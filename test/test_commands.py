

import pytest
import subprocess
import os

TEST_COMMANDS = (
    ("divio"),
    ("divio", "version"),
    ("divio", "doctor"),
    ("divio", "project"),
    ("divio", "project", "dashboard"),
#    ("divio", "project", "deploy"),
#    ("divio", "project", "deploy-log"),
#    ("divio", "project", "develop"),
    ("divio", "project", "env-vars"),
#    ("divio", "project", "export"),
#    ("divio", "project", "import"),
    ("divio", "project", "list"),
    ("divio", "project", "live"),
    ("divio", "project", "open"),
#    ("divio", "project", "pull"),
#    ("divio", "project", "push"),
#    ("divio", "project", "setup"), # already executed
    ("divio", "project", "status"),
    ("divio", "project", "up"),
    ("divio", "project", "stop"),
    ("divio", "project", "test"),
    ("divio", "project", "update"),

)



@pytest.mark.integration
@pytest.mark.parametrize("command",TEST_COMMANDS )
def test_call_commands(divio_project, command):
    completed_process = subprocess.run(command, cwd=divio_project)
    assert completed_process.returncode == 0
