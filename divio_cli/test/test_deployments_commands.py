import os

import pytest
from click.testing import CliRunner

from divio_cli import cli


TEST_PROJECT_ID = os.getenv("TEST_PROJECT_ID", None)
TEST_PROJECT_UUID = os.getenv("TEST_PROJECT_UUID", None)
TEST_PROJECT_DEPLOYMENT_UUID = os.getenv("TEST_PROJECT_DEPLOYMENT_UUID", None)

DEPLOYMENTS_COMMANDS = [
    ["app", "deployments"],
    ["app", "deployments", "list"],
    ["app", "deployments", "--remote-id", TEST_PROJECT_ID, "list"],
    ["app", "deployments", "--remote-id", TEST_PROJECT_UUID, "list"],
    ["app", "deployments", "list", "-e", "live"],
    ["app", "deployments", "list", "--all-envs"],
    ["app", "deployments", "-p", "list"],
    ["app", "deployments", "--json", "list"],
    ["app", "deployments", "list", "--limit", "1"],
    ["app", "deployments", "get", TEST_PROJECT_DEPLOYMENT_UUID],
    ["app", "deployments", "--json", "get", TEST_PROJECT_DEPLOYMENT_UUID],
    ["app", "deployments", "get-var", TEST_PROJECT_DEPLOYMENT_UUID, "STAGE"],
    [
        "app",
        "deployments",
        "--json",
        "get-var",
        TEST_PROJECT_DEPLOYMENT_UUID,
        "STAGE",
    ],
]


@pytest.mark.integration()
@pytest.mark.parametrize("command", DEPLOYMENTS_COMMANDS)
def test_call_deployment_commands(divio_project, command):
    runner = CliRunner()
    result = runner.invoke(cli.cli, command)
    assert result.exit_code == 0
