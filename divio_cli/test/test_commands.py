import pytest
from click.testing import CliRunner

from divio_cli import cli


NOI = "--noinput"
DBFILE = ".divio/local_db.sql"

TEST_COMMANDS_CLICK = [
    ["doctor"],
    ["doctor", "-m"],
    ["doctor", "-c", "login"],
    ["login", "--check"],
    ["app"],
    ["app", "dashboard"],
    ["app", "deploy", "test"],
    ["app", "deploy-log"],
    ["app", "list"],
    ["app", "export", "db"],
    ["app", "pull", "db"],
    ["app", "pull", "db", "test", "mysql"],
    ["app", "pull", "media"],
    ["app", "push", "db", NOI, "--keep-tempfile"],  # keep for next test
    ["app", "push", "db", NOI, "--dumpfile", DBFILE],
    ["app", "push", "db", "test", "mysql", NOI, "--keep-tempfile"],
    ["app", "push", "db", "test", "MYSQL", NOI, "--dumpfile", DBFILE],
    ["app", "push", "media", NOI],
    ["app", "logs", "test"],
    ["app", "status"],
    ["app", "update"],
    ["app", "service-instances", "list"],
    ["version"],
    ["version", "-s"],
    ["version", "-m"],
    ["regions", "list"],
    ["organisations", "list"],
]


@pytest.mark.integration()
@pytest.mark.parametrize("command", TEST_COMMANDS_CLICK)
def test_call_click_commands(divio_project, command):
    runner = CliRunner()
    result = runner.invoke(cli.cli, command)
    assert result.exit_code == 0, result.stdout
