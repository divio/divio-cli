import pytest
import subprocess
import os
TEST_PROJECT_DIR = "test/data"

def pytest_addoption(parser):
    parser.addoption("--test_project_name", action="store")



@pytest.fixture(scope="session")
def divio_project(request):
    """
    This fixture requires the `--test_project_name` command line parameter to
    checkout an actual project for the integration test.

    We try to setup up the first time and will not set it up again if it
    already exists.
    """
    name_value = request.config.option.test_project_name
    if  name_value is None:
        raise ValueError("project name for the test is not supplied. Please use `--test_project_name <name>` to specify one .")

    TEST_PROJECT_DIR_FULL_PATH = os.path.join(TEST_PROJECT_DIR, name_value)

    if not os.path.exists(TEST_PROJECT_DIR_FULL_PATH):
        subprocess.run(["divio", "project", "setup", name_value], cwd=TEST_PROJECT_DIR, check=True)
    return TEST_PROJECT_DIR_FULL_PATH
