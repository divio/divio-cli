import pytest
from click.testing import CliRunner

from divio_cli import cli


TEST_COMMANDS_CLICK = [
    ["doctor"],
    ["doctor", "-m"],
    ["doctor", "-c", "login"],
    ["login", "--check"],
    ["project"],
    ["project", "dashboard"],
    ["project", "deploy", "test"],
    ["project", "deploy-log"],
    ["project", "env-vars"],
    ["project", "list"],
    # ["project", "pull", "db"],
    # ("project", "push", "db", "--noinput"),
    ["project", "export", "db"],
    # ("project", "push", "db", "--noinput", "--dumpfile", "local_db.sql"),
    ["project", "pull", "media"],
    ["project", "push", "media", "--noinput"],
    ["project", "logs", "test"],
    ["project", "status"],
    ["project", "update"],
    ["version"],
    ["version", "-s"],
    ["version", "-m"],
]


@pytest.mark.integration
@pytest.mark.parametrize("command", TEST_COMMANDS_CLICK)
def test_call_click_commands(divio_project, command):
    runner = CliRunner()
    result = runner.invoke(cli.cli, command)
    print(result.output)
    assert result.exit_code == 0
