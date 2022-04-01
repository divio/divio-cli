import click
import pytest

from divio_cli import settings
from divio_cli.localdev import utils


def test_get_application_home(tmp_path):

    # Loud fail to get the aldryn file
    with pytest.raises(click.exceptions.ClickException):
        home = utils.get_application_home(str(tmp_path))

    # Silent fail to find the aldryn file
    home = utils.get_application_home(str(tmp_path), silent=True)
    assert not home

    p = tmp_path / settings.ALDRYN_DOT_FILE
    p.write_text("#Examplecontent")
    home = utils.get_application_home(str(tmp_path))
    assert home
