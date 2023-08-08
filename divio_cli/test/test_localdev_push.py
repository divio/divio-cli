from unittest.mock import MagicMock, mock_open, patch

import pytest

from divio_cli.localdev.push import PushBase, is_db_dump


@pytest.mark.parametrize(
    "content,postgres_res,mysql_res",
    [
        (b"\x50\x47\x44\x42\x44\x34\x34", True, False),
        (b"\x50\x47\x42\x44", False, False),
        (b"-- MariaDB dump 10.19  Distrib 10.5.17-MariaDB\n--", True, True),
        (b"-- MySQL DUMP with some distrib", True, True),
        (b"--\n-- PostgreSQL database dUmp\n--", True, True),
        (b"MySQL dump", False, False),
        (b"-- d u m p", False, False),
    ],
)
def test_is_db_dump(content, postgres_res, mysql_res):
    with patch("builtins.open", mock_open(read_data=content)) as file:
        assert is_db_dump(file, "fsm-postgres") == postgres_res
        assert is_db_dump(file, "fsm-mysql") == mysql_res


@pytest.mark.parametrize(
    "local_file,cleanup,verify_called,export_called,cleanup_called",
    [
        (None, True, False, True, True),
        (None, False, False, True, False),
        ("local_file.sql", True, True, False, True),
        ("local_file.sql", False, True, False, False),
    ],
)
def test_steps(
    local_file, cleanup, verify_called, export_called, cleanup_called
):
    pusher = PushBase(*[""] * 9)
    pusher.__class__.backup_type = "db"

    pusher.verify_step = MagicMock()
    pusher.export_step = MagicMock()
    pusher.upload_step = MagicMock()
    pusher.restore_step = MagicMock()
    pusher.cleanup_step = MagicMock()

    pusher.run(local_file=local_file, cleanup=cleanup)
    assert pusher.verify_step.called == verify_called
    assert pusher.export_step.called == export_called
    pusher.upload_step.assert_called()
    pusher.restore_step.assert_called()
    assert pusher.cleanup_step.called == cleanup_called


def test_restore_step(monkeypatch):
    PushBase(*[""] * 9)
