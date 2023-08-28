import os
import subprocess

import pytest


TEST_PROJECT_ID = os.getenv("TEST_PROJECT_ID", None)
TEST_PROJECT_UUID = os.getenv("TEST_PROJECT_UUID", None)

ENVIRONMENT_VARIABLES_COMMANDS = [
    ["app", "environment-variables"],
    ["app", "env-vars", "list"],
    ["app", "env-vars", "--remote-id", TEST_PROJECT_ID, "list"],
    ["app", "env-vars", "--remote-id", TEST_PROJECT_UUID, "list"],
    ["app", "env-vars", "list", "-e", "live"],
    ["app", "env-vars", "list", "--all-envs"],
    ["app", "env-vars", "-p", "list"],
    ["app", "env-vars", "list", "--limit", "1"],
    ["app", "env-vars", "--json", "list"],
    ["app", "env-vars", "--txt", "list"],
    ["app", "env-vars", "get", "SIMPLE_VAR"],
    ["app", "env-vars", "get", "SIMPLE_VAR", "--all-envs"],
    ["app", "env-vars", "get", "SIMPLE_VAR", "--all-envs", "--limit", "1"],
    ["app", "env-vars", "--json", "get", "SIMPLE_VAR"],
    ["app", "env-vars", "--txt", "get", "SIMPLE_VAR"],
]


@pytest.mark.integration()
@pytest.mark.parametrize("command", ENVIRONMENT_VARIABLES_COMMANDS)
def test_call_click_commands(divio_project, command):
    exitcode = subprocess.check_call(["divio", *command])

    assert exitcode == 0
