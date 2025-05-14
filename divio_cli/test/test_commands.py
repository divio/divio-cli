import os
import shlex
import shutil
import subprocess
from tempfile import TemporaryDirectory

import pytest
from click.testing import CliRunner

from divio_cli import cli
from divio_cli.cloud import WritableNetRC


NOI = "--noinput"
DBFILE = ".divio/local_db.sql"

TEST_COMMANDS_CLICK = [
    (0, "doctor"),
    (0, "doctor -m"),
    (0, "doctor -c login"),
    (0, "login --check"),
    (2, "app"),
    (0, "app dashboard"),
    (0, "app deploy test"),
    (0, "app deploy-log"),
    (0, "app list"),
    (0, "app pull db"),
    (0, "app push db --noinput"),
    (0, "app export db"),
    (0, "app push db --noinput --dumpfile local_db.sql"),
    (0, "app pull media"),
    (0, "app push media --noinput"),
    (0, "app logs test"),
    (0, "app status"),
    (0, "app update"),
    (0, "app service-instances list"),
    (0, "version"),
    (0, "version -s"),
    (0, "version -m"),
    (0, "regions list"),
    (0, "organisations list"),
]


@pytest.mark.integration()
@pytest.mark.parametrize("command", TEST_COMMANDS_CLICK)
def test_call_click_commands(divio_project, command):
    expected_exitcode, command = command

    if expected_exitcode == 2:
        with pytest.raises(subprocess.CalledProcessError):
            subprocess.check_call(["divio", *shlex.split(command)])

    else:
        exitcode = subprocess.check_call(["divio", *shlex.split(command)])
        assert exitcode == expected_exitcode


@pytest.mark.integration()
def test_logout_command(divio_project):
    """
    The logout command has to be tested separately, and using a temporary
    netrc, because the following tests require the cli to be logged in.

    This test copies the global netrc into a temporary directory, sets the
    temporary netrc globally, and then checks if the "logout" command causes
    the "login --check" command to return an exit code of 1.
    """

    with TemporaryDirectory() as temporary_directory:
        original_netrc_path = WritableNetRC.get_netrc_path()

        temporary_netrc_path = os.path.join(
            temporary_directory,
            os.path.basename(original_netrc_path),
        )

        shutil.copy(original_netrc_path, temporary_netrc_path)

        try:
            os.environ["NETRC_PATH"] = temporary_netrc_path

            runner = CliRunner()

            result = runner.invoke(cli.cli, ["login", "--check"])
            assert result.exit_code == 0, result.stdout

            result = runner.invoke(cli.cli, ["logout", "--non-interactive"])
            assert result.exit_code == 0, result.stdout

            result = runner.invoke(cli.cli, ["login", "--check"])
            assert result.exit_code == 1, result.stdout

        finally:
            os.environ.pop("NETRC_PATH")
