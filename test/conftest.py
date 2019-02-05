import pytest
import subprocess
import os

PROJECT_NAME = "ci-test-project-do-not-delete"
TEST_PROJECT_DIR = "test/data"

@pytest.fixture(scope="session")
def divio_project():

    if not os.path.exists(TEST_PROJECT_DIR):
        subprocess.run(["divio", "project", "setup", PROJECT_NAME], cwd=TEST_PROJECT_DIR)
        completed_process = subprocess.run(command)
        assert completed_process.returncode == 0
    return os.path.join(TEST_PROJECT_DIR, PROJECT_NAME)
