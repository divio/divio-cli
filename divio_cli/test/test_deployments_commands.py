import pytest
from click.testing import CliRunner

from divio_cli import cli


APP_ID = "75584"
APP_UUID = "iqbd4lzcnjczfc42qbidn6safu"
DEPLOYMENT_UUID = "zb3ujcz6kzcjph46tv6vlo4aw4"

DEPLOYMENTS_COMMANDS = [
    ["app", "deployments"],
    ["app", "deployments", "list"],
    ["app", "deployments", "--remote-id", APP_ID, "list"],
    ["app", "deployments", "--remote-id", APP_UUID, "list"],
    ["app", "deployments", "list", "-e", "live"],
    ["app", "deployments", "list", "--all-envs"],
    ["app", "deployments", "-p", "list"],
    ["app", "deployments", "--json", "list"],
    ["app", "deployments", "list", "--limit", "1"],
    ["app", "deployments", "get", DEPLOYMENT_UUID],
    ["app", "deployments", "--json", "get", DEPLOYMENT_UUID],
    ["app", "deployments", "get-var", DEPLOYMENT_UUID, "STAGE"],
    ["app", "deployments", "--json", "get-var", DEPLOYMENT_UUID, "STAGE"],
]


@pytest.mark.integration
@pytest.mark.parametrize("command", DEPLOYMENTS_COMMANDS)
def test_call_click_commands(divio_project, command):
    runner = CliRunner()
    result = runner.invoke(cli.cli, command)
    assert result.exit_code == 0
