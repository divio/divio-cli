

import pytest
import subprocess
import os

TEST_COMMANDS = (
    ("divio"),
#   ("divio", "addon"),
#   ("divio", "boilerplate"),
    ("divio", "doctor"),
    ("divio", "doctor", "-m"),
    ("divio", "doctor", "-c", "login"),
    ("divio", "login", "--check"),
#    ("divio", "login"),
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
#    ("divio", "project", "pull"),
#    ("divio", "project", "push"),
#    ("divio", "project", "setup"), # already executed
    ("divio", "project", "status"),
    ("divio", "project", "up"),
    ("divio", "project", "open"),
    ("divio", "project", "stop"),
    ("divio", "project", "test"),
    ("divio", "project", "update"),
    ("divio", "version"),
    ("divio", "version", "-s"),  # don't check PyPI for newer version
    ("divio", "version", "-m"),  # Show this message and exit.
)



@pytest.mark.integration
@pytest.mark.parametrize("command",TEST_COMMANDS )
def test_call_commands(divio_project, command):
    completed_process = subprocess.run(command, cwd=divio_project)
    assert completed_process.returncode == 0


