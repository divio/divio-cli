from enum import Enum
from time import sleep
from typing import Optional, Tuple

from ..cloud import CloudClient
from . import utils


class Type(str, Enum):
    MEDIA = "STORAGE"
    DB = "DATABASE"


def create_backup(
    client: CloudClient,
    website_id: str,
    environment: str,
    type: Type,
    prefix: Optional[str] = None,
) -> Tuple[str, str]:
    """
    Request a backup for the service instance matching type and prefix.

    The service instance UUID is found using the website_id, environment,
    type and prefix parameters. If none is found, an error is thrown.
    The method only reurns once the backup is ready.
    """
    # Find the matching service instance for the given service type
    env_uuid = client.get_environment(website_id, environment)["uuid"]
    si_uuid = client.get_service_instance(type, env_uuid, prefix)["uuid"]

    # Create a backup
    response = client.create_backup(env_uuid, si_uuid)
    backup_uuid = response["uuid"]
    if not backup_uuid:
        utils.exit(response.get("result") or "")

    # Wait for the backup to complete
    backup = {"success": "PARTIAL"}
    while backup.get("success") == "PARTIAL":
        sleep(2)
        backup = client.get_backup(backup_uuid)
    if backup.get("success") != "SUCCESS":
        message = "Backup failed"
        if backup.get("service_instance_backups", []):
            try:
                # Get more information about the error
                backup_si_uuid = backup["service_instance_backups"][0]
                backup_si = client.get_service_instance_backup(backup_si_uuid)
                message += f": {backup_si['errors']}"
            except:
                pass
        utils.exit(message)
    if not backup.get("service_instance_backups", []):
        utils.exit("No service instance backup was found.")

    return backup["uuid"], backup["service_instance_backups"][0]


def get_backup_uuid_from_service_backup(
    client: CloudClient,
    backup_si_uuid: str,
    service_type: Type,
) -> str:
    backup_si = client.get_service_instance_backup(backup_si_uuid)
    if not backup_si:
        utils.exit("Invalid service instance backup UUID provided.")

    if not backup_si.get("ended_at"):
        utils.exit("The provided service instance backup is still running.")
    if backup_si.get("errors"):
        utils.exit(
            "The provided service instance backup has errors:"
            f" {backup_si['errors']}."
        )
    if backup_si.get("service_type") != service_type:
        utils.exit(
            "The provided service instance backup is for a different service type."
        )
    return backup_si["backup"]


def create_backup_download_url(
    client: CloudClient,
    backup_uuid: str,
    backup_si_uuid: str,
) -> str:
    """
    Get a download URL for a given backup UUID and service instance backup UUID.
    The service instance backup must be part of the backup.
    Use get_backup_uuid_from_service_backup or get_service_backup_uuid_from_backup
    to get one given the other.
    """

    # request backup download
    (
        backup_download_uuid,
        backup_download_si_uuid,
    ) = client.create_backup_download(backup_uuid, backup_si_uuid)

    if not backup_download_uuid or not backup_download_si_uuid:
        utils.exit("Error while creating backup download")

    # wait for the backup download to complete
    backup_download_si = {"ended_at": None}
    while not backup_download_si.get("ended_at"):
        sleep(2)
        backup_download_si = client.get_backup_download_service_instance(
            backup_download_si_uuid
        )
    if backup_download_si.get("errors"):
        utils.exit(f"Backup download failed: {backup_download_si['errors']}")

    return backup_download_si["download_url"]
