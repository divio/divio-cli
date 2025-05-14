import os
import shlex
import subprocess

import pytest


TEST_PROJECT_ID = os.getenv("TEST_PROJECT_ID", None)
TEST_PROJECT_UUID = os.getenv("TEST_PROJECT_UUID", None)
TEST_PROJECT_DEPLOYMENT_UUID = os.getenv("TEST_PROJECT_DEPLOYMENT_UUID", None)

DEPLOYMENTS_COMMANDS = [
    (2, "app deployments"),
    (0, "app deployments list"),
    (0, f"app deployments list --remote-id {TEST_PROJECT_ID}"),
    (0, f"app deployments list --remote-id {TEST_PROJECT_UUID}"),
    (0, "app deployments list -e live"),
    (0, "app deployments list --all-envs"),
    (0, "app deployments -p list"),
    (0, "app deployments --json list"),
    (0, "app deployments list --limit 1"),
    (0, f"app deployments get {TEST_PROJECT_DEPLOYMENT_UUID}"),
    (0, f"app deployments --json get {TEST_PROJECT_DEPLOYMENT_UUID}"),
    (0, f"app deployments get-var {TEST_PROJECT_DEPLOYMENT_UUID} STAGE"),
    (
        0,
        f"app deployments --json get-var {TEST_PROJECT_DEPLOYMENT_UUID} STAGE",
    ),
]


@pytest.mark.integration()
@pytest.mark.parametrize("command", DEPLOYMENTS_COMMANDS)
def test_call_click_commands(divio_project, command):
    expected_exitcode, command = command

    if expected_exitcode == 2:
        with pytest.raises(subprocess.CalledProcessError):
            subprocess.check_call(["divio", *shlex.split(command)])

    else:
        exitcode = subprocess.check_call(["divio", *shlex.split(command)])
        assert exitcode == expected_exitcode
