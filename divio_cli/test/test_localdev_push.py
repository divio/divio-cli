from unittest.mock import mock_open, patch

import pytest

from divio_cli.localdev.push import is_db_dump


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
