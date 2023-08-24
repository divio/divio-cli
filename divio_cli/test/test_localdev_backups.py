from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest

from divio_cli.exceptions import DivioException
from divio_cli.localdev import backups


_BACKUP_SUCCESS = {
    "state": "COMPLETED",
    "success": "SUCCESS",
    "uuid": "<backup-uuid>",
    "service_instance_backups": ["<si-uuid>"],
}


def test_create_backup():
    client = MagicMock()

    client.get_environment.return_value = {"uuid": "<env_uuid>"}
    client.get_service_instance.return_value = {"uuid": "<si_uuid>"}
    client.create_backup.return_value = {"uuid": "<uuid>"}
    client.get_backup.return_value = _BACKUP_SUCCESS

    ret = backups.create_backup(
        client, "<website_id>", "environment", backups.Type.DB
    )
    assert ret == ("<backup-uuid>", "<si-uuid>")

    assert client.create_backup.called
    args = client.create_backup.call_args[1]
    assert args["environment_uuid"] == "<env_uuid>"
    assert args["service_instance_uuid"] == "<si_uuid>"
    assert args["notes"] == "Divio CLI pull"
    assert args["delete_at"] - (
        datetime.utcnow() + timedelta(minutes=60)
    ) < timedelta(seconds=1)


@pytest.mark.parametrize(
    ("backup_si", "error"),
    [
        ({}, "Invalid service instance backup provided."),
        (
            {"backup": "123"},
            "The provided service instance backup is still running.",
        ),
        (
            {"backup": "123", "ended_at": None},
            "The provided service instance backup is still running.",
        ),
        (
            {"backup": "123", "ended_at": "<date>", "errors": "oops"},
            "The provided service instance backup completed with errors: oops.",
        ),
        (
            {
                "backup": "123",
                "ended_at": "<date>",
                "errors": None,
                "service_type": "wrong",
            },
            "The provided service instance backup is for a different service type.",
        ),
        (
            {
                "backup": "123",
                "ended_at": "<date>",
                "errors": None,
                "service_type": "correct",
            },
            None,
        ),
    ],
)
def test_get_backup_uuid_from_service_backup(backup_si, error):
    client = MagicMock()
    client.get_service_instance_backup.return_value = backup_si
    args = {
        "client": client,
        "backup_si_uuid": "<uuid>",
        "service_type": "correct",
    }

    if error:
        with pytest.raises(DivioException) as excinfo:
            backups.get_backup_uuid_from_service_backup(**args)
        assert str(excinfo.value) == error
    else:
        ret = backups.get_backup_uuid_from_service_backup(**args)
        assert ret == "123"


def test_upload_backup(monkeypatch):
    boto3 = MagicMock()
    monkeypatch.setattr("divio_cli.localdev.backups.boto3", boto3)

    client = MagicMock()
    client.backup_upload_request.return_value = {
        "uuid": "<backup-uuid>",
        "results": {
            "<si-uuid>": {
                "handler": "s3-sts-v1",
                "finish_url": "https://example.com/finish",
                "upload_parameters": {
                    "aws_access_key_id": "aws_access_key_id",
                    "aws_secret_access_key": "aws_secret_access_key",
                    "aws_session_token": "aws_session_token",
                    "bucket": "bucket",
                    "key": "key",
                },
            }
        },
    }
    client.finish_backup_upload.return_value = {"uuid": "<backup-uuid>"}
    client.get_backup.return_value = _BACKUP_SUCCESS

    ret = backups.upload_backup(client, "<env-uuid>", "<si-uuid>", "file")
    assert ret == ("<backup-uuid>", "<si-uuid>")

    boto3.client.assert_called_with(
        "s3",
        aws_access_key_id="aws_access_key_id",
        aws_secret_access_key="aws_secret_access_key",
        aws_session_token="aws_session_token",
    )
    boto3.client.return_value.upload_file.assert_called_with(
        "file", Bucket="bucket", Key="key"
    )
    client.finish_backup_upload.assert_called_with(
        "https://example.com/finish"
    )


def test_upload_backup_wrong_handler():
    client = MagicMock()
    client.backup_upload_request.return_value = {
        "uuid": "<backup-uuid>",
        "results": {
            "<si-uuid>": {
                "handler": "wrong",
                "finish_url": "https://example.com/finish",
                "upload_parameters": {},
            }
        },
    }

    with pytest.raises(DivioException) as excinfo:
        backups.upload_backup(client, "<env-uuid>", "<si-uuid>", "file")
    assert str(excinfo.value) == "Unsupported backend: wrong"


@pytest.mark.parametrize(
    ("statuses", "error_message"),
    [
        ([("", ""), ("<date>", "")], None),
        ([("", ""), ("<date>", "error!")], "Backup download failed: error!"),
        ([("<date>", "")], None),
        ([("<date>", "foo error")], "Backup download failed: foo error"),
    ],
)
def test_create_backup_download_url(statuses, error_message):
    client = MagicMock()
    client.create_backup_download.return_value = ("<backup_uuid>", "<si_uuid>")
    client.get_backup_download_service_instance.side_effect = [
        {
            "uuid": "<download_si_uuid>",
            "ended_at": ended_at,
            "errors": error,
            "download_url": "https://example.com/download",
        }
        for ended_at, error in statuses
    ]
    args = {"client": client, "backup_uuid": "<b>", "backup_si_uuid": "<si>"}

    if error_message:
        with pytest.raises(DivioException) as excinfo:
            backups.create_backup_download_url(**args)
        assert str(excinfo.value) == error_message

    else:
        uuid = backups.create_backup_download_url(**args)
        assert uuid == "https://example.com/download"


@pytest.mark.parametrize(
    ("statuses", "ok"),
    [
        ([(False, "PARTIAL"), (True, "SUCCESS")], True),
        ([(False, "SUCCESS"), (True, "FAILURE")], False),
        ([(True, "PARTIAL")], False),
        ([(True, None)], False),
    ],
)
def test__wait_for_backup_to_complete(statuses, ok):
    client = MagicMock()
    client.get_backup.side_effect = [
        {
            "state": "COMPLETED" if finished else "WORKING",
            "success": success,
            "uuid": "bk_uuid",
            "service_instance_backups": ["si_uuid"],
        }
        for finished, success in statuses
    ]
    client.get_service_instance_backup.side_effect = Exception()

    if ok:
        ret = backups._wait_for_backup_to_complete(client, "<uuid>")
        assert ret == ("bk_uuid", "si_uuid")
    else:
        with pytest.raises(DivioException) as excinfo:
            backups._wait_for_backup_to_complete(client, "<uuid>")

        assert f"Backup failed: success={statuses[-1][-1]}" in str(
            excinfo.value
        )


@pytest.mark.parametrize(
    ("si_backups", "si_details", "message"),
    [
        (
            ["si_uuid", "si_uuid_2"],
            [{"errors": "one"}, {"errors": "two"}],
            "message: success=FAILURE, one",
        ),
        (["si_uuid"], Exception(), "message: success=FAILURE"),
        (["si_uuid"], {}, "message: success=FAILURE"),
    ],
)
def test__wait_for_backup_to_complete_si_error(
    si_backups, si_details, message
):
    client = MagicMock()
    client.get_backup.return_value = {
        "state": "COMPLETED",
        "success": "FAILURE",
        "uuid": "bk_uuid",
        "service_instance_backups": [si_backups],
    }

    client.get_service_instance_backup = Mock(side_effect=si_details)

    with patch("time.sleep"):
        with pytest.raises(DivioException) as excinfo:
            backups._wait_for_backup_to_complete(
                client, "<uuid>", message="message"
            )
    assert message in str(excinfo.value)


@pytest.mark.parametrize("si_backups", [[], None])
def test__wait_for_backup_to_complete_no_si(si_backups):
    client = MagicMock()
    client.get_backup.return_value = {
        "state": "COMPLETED",
        "success": "SUCCESS",
        "uuid": "bk_uuid",
        "service_instance_backups": si_backups,
    }

    with pytest.raises(DivioException) as excinfo:
        backups._wait_for_backup_to_complete(
            client, "<uuid>", message="message"
        )
    assert "No service instance backup was found." in str(excinfo.value)
