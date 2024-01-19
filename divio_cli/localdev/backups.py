from __future__ import annotations

import contextlib
import os
import time
from datetime import datetime, timedelta, timezone
from enum import Enum

import boto3

from azure.storage.blob import BlobClient

import requests

from divio_cli.exceptions import DivioException
from divio_cli.utils import pretty_size

from ..cloud import CloudClient


BACKUP_RETENTION = timedelta(hours=1)
UPLOAD_BACKUP_NOTE = "Divio CLI push"
DOWNLOAD_BACKUP_NOTE = "Divio CLI pull"


class Type(str, Enum):
    MEDIA = "STORAGE"
    DB = "DATABASE"


def get_backup_delete_at() -> datetime:
    """Get the date at which a backup created now should be deleted."""
    return datetime.now(tz=timezone.utc) + BACKUP_RETENTION


def create_backup(
    client: CloudClient,
    application_uuid: str,
    environment: str,
    type: Type,
    prefix: str | None = None,
) -> tuple[str, str]:
    """
    Trigger a backup for the service instance matching `type` and `prefix`.

    The service instance UUID is found using the application_uuid, environment,
    type and prefix parameters. If none (or more than one) is found,
    an error is thrown. The function only returns once the backup is ready.

    Return a backup UUID and a service instance backup UUID
    valid for an hour.
    """
    # Find the matching service instance for the given service type
    env_uuid = client.get_environment(application_uuid, environment)["uuid"]
    si_uuid = client.get_service_instance(type, env_uuid, prefix)["uuid"]

    # Create a backup
    response = client.create_backup(
        environment_uuid=env_uuid,
        service_instance_uuid=si_uuid,
        notes=DOWNLOAD_BACKUP_NOTE,
        delete_at=get_backup_delete_at(),
    )
    backup_uuid = response["uuid"]
    return _wait_for_backup_to_complete(client, backup_uuid)


def get_backup_uuid_from_service_backup(
    client: CloudClient,
    backup_si_uuid: str,
    service_type: Type,
) -> str:
    """
    Find the backup UUID a given service instance backup belongs to.
    """
    backup_si = client.get_service_instance_backup(backup_si_uuid)
    if not backup_si:
        raise DivioException("Invalid service instance backup provided.")

    if not backup_si.get("ended_at"):
        raise DivioException(
            "The provided service instance backup is still running."
        )
    if backup_si.get("errors"):
        raise DivioException(
            "The provided service instance backup completed with errors:"
            f" {backup_si['errors']}."
        )
    if backup_si.get("service_type") != service_type:
        raise DivioException(
            "The provided service instance backup is for a different service type."
        )
    return backup_si["backup"]


def upload_backup(
    client: CloudClient,
    environment_uuid: str,
    si_uuid: str,
    local_file: str,
) -> tuple[str, str]:
    """
    Upload a local file to Divio. This creates as a backup
    (+service instance backup) that can be later restored.

    Return a backup UUID and a service instance backup UUID
    valid for an hour.
    """
    res = client.backup_upload_request(
        environment=environment_uuid,
        service_intance_uuids=[si_uuid],
        notes=UPLOAD_BACKUP_NOTE,
        delete_at=get_backup_delete_at(),
    )

    backup_uuid = res["uuid"]
    params = res["results"][si_uuid]
    upload_params = params["upload_parameters"]

    if params["handler"] == "s3-sts-v1":
        _upload_backup_aws(upload_params, local_file)
    elif params["handler"] == "az-sas-v1":
        _upload_backup_azure(upload_params, local_file)
    elif params["handler"] == "exo-presigned-v1":
        _upload_backup_exoscale(upload_params, local_file)
    else:
        raise DivioException(f"Unsupported backend: {params['handler']}")

    client.finish_backup_upload(params["finish_url"])
    return _wait_for_backup_to_complete(
        client, backup_uuid, message="Backup upload failed"
    )


def _upload_backup_aws(upload_params, local_file):
    boto3.client(
        "s3",
        aws_access_key_id=upload_params["aws_access_key_id"],
        aws_secret_access_key=upload_params["aws_secret_access_key"],
        aws_session_token=upload_params["aws_session_token"],
    ).upload_file(
        local_file,
        Bucket=upload_params["bucket"],
        Key=upload_params["key"],
    )


def _upload_backup_azure(upload_params, local_file):
    with open(local_file, "rb") as fh:
        BlobClient.from_blob_url(blob_url=upload_params["url"]).upload_blob(
            fh, overwrite=True, max_concurrency=10
        )


def _upload_backup_exoscale(upload_params, local_file):
    max_size = upload_params["max_file_size"]
    size = os.stat(local_file).st_size
    if size > max_size:
        raise DivioException(
            f"{local_file.split('/')[-1]} is {pretty_size(size)}, "
            f"which is above the upload size limit of {pretty_size(max_size)}."
        )
    with open(local_file, "rb") as fh:
        requests.put(upload_params["url"], data=fh).raise_for_status()


def create_backup_download_url(
    client: CloudClient,
    backup_uuid: str,
    backup_si_uuid: str,
) -> str:
    """
    Get a download URL for a given backup UUID and service instance backup UUID.
    The service instance backup must be part of the backup.
    See get_backup_uuid_from_service_backup or create_backup.
    """

    # Create a backup download
    (
        backup_download_uuid,
        backup_download_si_uuid,
    ) = client.create_backup_download(backup_uuid, backup_si_uuid)

    if not backup_download_uuid or not backup_download_si_uuid:
        raise DivioException("Error while creating backup download")

    # Wait for the backup download to complete
    backup_download_si = {"ended_at": None}
    while not backup_download_si.get("ended_at"):
        time.sleep(2)
        backup_download_si = client.get_backup_download_service_instance(
            backup_download_si_uuid
        )
    if backup_download_si.get("errors"):
        raise DivioException(
            f"Backup download failed: {backup_download_si['errors']}"
        )

    return backup_download_si["download_url"]


def _wait_for_backup_to_complete(
    client: CloudClient, backup_uuid: str, message: str = "Backup failed"
) -> tuple[str, str]:
    # Wait for the backup to complete
    backup = {"state": ""}
    while backup.get("state") != "COMPLETED":
        time.sleep(2)
        backup = client.get_backup(backup_uuid)

    success = backup.get("success")
    si_backups = backup.get("service_instance_backups", [])
    if success != "SUCCESS":
        message += f": success={success}"
        if si_backups:
            with contextlib.suppress(Exception):
                # Try to get more information about the error
                si_backup = client.get_service_instance_backup(si_backups[0])
                errors = si_backup.get("errors", None)
                if errors:
                    message += f", {errors}"
        raise DivioException(message)

    if not si_backups:
        raise DivioException("No service instance backup was found.")

    return backup["uuid"], backup["service_instance_backups"][0]
