from unittest.mock import MagicMock, Mock, patch

import pytest

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
def test_wait_for_backup_to_complete(monkeypatch, statuses, ok):
    mockexit = MagicMock()
    monkeypatch.setattr("divio_cli.localdev.utils.exit", mockexit)

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

    ret = backups._wait_for_backup_to_complete(client, "<uuid>")
    if ok:
        assert ret == ("bk_uuid", "si_uuid")
    else:
        mockexit.assert_called_once_with(
            f"Backup failed: success={statuses[-1][-1]}"
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
        ([], None, "No service instance backup was found."),
        (None, None, "No service instance backup was found."),
    ],
)
def test_wait_for_backup_to_complete_error(
    monkeypatch, si_backups, si_details, message
):
    mockexit = MagicMock()
    monkeypatch.setattr("divio_cli.localdev.utils.exit", mockexit)

    client = MagicMock()
    client.get_backup = Mock(
        return_value={
            "state": "COMPLETED",
            "success": "FAILURE",
            "uuid": "bk_uuid",
            "service_instance_backups": [si_backups],
        }
    )
    client.get_service_instance_backup = Mock(side_effect=si_details)
    try:
        with patch("time.sleep"):
            backups._wait_for_backup_to_complete(
                client, "<uuid>", message="message"
            )
        mockexit.assert_called_once_with(message)
    except:
        pass
