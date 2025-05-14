import os
import shlex
import subprocess

import pytest


TEST_PROJECT_ID = os.getenv("TEST_PROJECT_ID", None)
TEST_PROJECT_UUID = os.getenv("TEST_PROJECT_UUID", None)

ENVIRONMENT_VARIABLES_COMMANDS = [
    (2, "app environment-variables"),
    (0, "app env-vars list"),
    (0, f"app env-vars list --remote-id {TEST_PROJECT_ID}"),
    (0, f"app env-vars list --remote-id {TEST_PROJECT_UUID}"),
    (0, "app env-vars list -e live"),
    (0, "app env-vars list --all-envs"),
    (0, "app env-vars -p list"),
    (0, "app env-vars list --limit 1"),
    (0, "app env-vars --json list"),
    (0, "app env-vars --txt list"),
    (0, "app env-vars get SIMPLE_VAR"),
    (0, "app env-vars get SIMPLE_VAR --all-envs"),
    (0, "app env-vars get SIMPLE_VAR --all-envs --limit 1"),
    (0, "app env-vars --json get SIMPLE_VAR"),
    (0, "app env-vars --txt get SIMPLE_VAR"),
]


@pytest.mark.integration()
@pytest.mark.parametrize("command", ENVIRONMENT_VARIABLES_COMMANDS)
def test_call_click_commands(divio_project, command):
    expected_exitcode, command = command

    if expected_exitcode == 2:
        with pytest.raises(subprocess.CalledProcessError):
            subprocess.check_call(["divio", *shlex.split(command)])

    else:
        exitcode = subprocess.check_call(["divio", *shlex.split(command)])
        assert exitcode == expected_exitcode
