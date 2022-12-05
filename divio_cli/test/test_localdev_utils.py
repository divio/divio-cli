import os

import click
import pytest

from divio_cli import settings
from divio_cli.localdev import utils


def test_get_application_home(tmp_path):

    # Loud fail to get the aldryn file
    with pytest.raises(click.exceptions.ClickException):
        home = utils.get_application_home(str(tmp_path))

    p = tmp_path / settings.ALDRYN_DOT_FILE
    p.write_text("#Examplecontent")
    home = utils.get_application_home(str(tmp_path))
    assert home


@pytest.mark.parametrize(
    "is_windows",
    [
        False,
        True,
    ],
)
def test_get_docker_compose_filename_does_not_exist(
    tmp_path, is_windows, monkeypatch
):
    monkeypatch.setattr(utils, "is_windows", lambda: is_windows)

    with pytest.raises(RuntimeError):
        utils.get_docker_compose_filename(tmp_path)


@pytest.mark.parametrize(
    "is_windows,create_windows,expected_stem",
    [
        (False, False, "docker-compose"),
        (True, False, "docker-compose-windows"),
        (False, True, "docker-compose"),
        (True, True, "docker-compose-windows"),
    ],
)
def test_get_docker_compose_filename_only_unix(
    tmp_path,
    is_windows,
    create_windows,
    monkeypatch,
    expected_stem,
    docker_compose_extension,
):
    monkeypatch.setattr(utils, "is_windows", lambda: is_windows)

    with open(
        os.path.join(tmp_path, f"docker-compose.{docker_compose_extension}"),
        "w",
    ) as fh:
        fh.write("unix: {}")

    if create_windows:
        with open(
            os.path.join(
                tmp_path, f"docker-compose-windows.{docker_compose_extension}"
            ),
            "w",
        ) as fh:
            fh.write("windows: {}")

    filename = utils.get_docker_compose_filename(tmp_path)
    assert filename == os.path.join(
        tmp_path, f"{expected_stem}.{docker_compose_extension}"
    )
    assert os.path.exists(filename)
    with open(filename) as fh:
        assert fh.read().strip() == (
            "windows: {}" if is_windows and create_windows else "unix: {}"
        )
