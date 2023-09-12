import pytest

from divio_cli import settings
from divio_cli.exceptions import (
    ConfigurationNotFound,
    DivioException,
    DivioWarning,
    DockerComposeDoesNotExist,
)
from divio_cli.localdev import utils


def test_get_application_home(tmp_path):

    # Should fail to get the aldryn file
    with pytest.raises(ConfigurationNotFound):
        home = utils.get_application_home(str(tmp_path))

    # Silent fail to find the aldryn file
    home = utils.get_application_home(str(tmp_path), silent=True)
    assert not home

    p = tmp_path / settings.ALDRYN_DOT_FILE
    p.write_text("#Examplecontent")
    home = utils.get_application_home(str(tmp_path))
    assert home


@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        (ValueError(), ""),
        (RuntimeError("oops"), "oops"),
        (DivioException(), " error!\n"),
        (DivioWarning("oops"), " warning!\noops"),
        (
            DockerComposeDoesNotExist(),
            " error!\ndocker-compose.yml does not exist.",
        ),
    ],
)
def test_timed_step_exception(exception, expected):
    with pytest.raises(Exception) as excinfo:
        with utils.TimedStep("test"):
            raise exception

    assert isinstance(excinfo.value, exception.__class__)
    assert str(excinfo.value) == expected
