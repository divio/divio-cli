import pytest
from click.testing import CliRunner

from divio_cli import cli


# 10 12 14
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
    ["app", "pull", "db"],
    ["app", "push", "db", "--noinput"],
    ["app", "export", "db"],
    ["app", "push", "db", "--keep-tempfile"],  # keep file for next test
    ["app", "push", "db", "--noinput", "--dumpfile", "local_db.sql"],
    [
        "app",
        "push",
        "db",
        "test",
        "MYSQL",
        "--keep-tempfile",
    ],  # keep file for next test
    [
        "app",
        "push",
        "db",
        "test",
        "MYSQL",
        "--noinput",
        "--dumpfile",
        "local_db.sql",
    ],
    ["app", "pull", "media"],
    ["app", "push", "media", "--noinput"],
    ["app", "logs", "test"],
    ["app", "status"],
    ["app", "update"],
    ["version"],
    ["version", "-s"],
    ["version", "-m"],
]


@pytest.mark.integration
@pytest.mark.parametrize("command", TEST_COMMANDS_CLICK)
def test_call_click_commands(divio_project, command):
    runner = CliRunner()
    result = runner.invoke(cli.cli, command)
    assert result.exit_code == 0, result.stdout
