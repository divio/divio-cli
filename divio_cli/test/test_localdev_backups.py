from unittest.mock import MagicMock, Mock, patch

import pytest

from divio_cli.exceptions import DivioException
from divio_cli.localdev import backups


@pytest.mark.parametrize(
    "statuses,ok",
    [
        ([(False, "PARTIAL"), (True, "SUCCESS")], True),
        ([(False, "SUCCESS"), (True, "FAILURE")], False),
        ([(True, "PARTIAL")], False),
        ([(True, None)], False),
    ],
)
def test_wait_for_backup_to_complete(statuses, ok):
    side_effects = [
        {
            "state": "COMPLETED" if finished else "WORKING",
            "success": success,
            "uuid": "bk_uuid",
            "service_instance_backups": ["si_uuid"],
        }
        for finished, success in statuses
    ]
    client = MagicMock()
    client.get_backup = Mock(side_effect=side_effects)
    client.get_service_instance_backup = Mock(side_effect=Exception())

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
    "si_backups,si_details,message",
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
def test_wait_for_backup_to_complete_si_error(si_backups, si_details, message):
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
def test_wait_for_backup_to_complete_no_si(si_backups):
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
