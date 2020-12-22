import os
import subprocess

import pytest


def pytest_addoption(parser):
    parser.addoption("--testprojectname", action="store")
    parser.addoption(
        "--testprojectdirectory", action="store", default="test/data"
    )


@pytest.fixture(scope="session")
def divio_project(request):
    """
    This fixture requires the `--test_project_name` command line parameter to
    checkout an actual project for the integration test.

    We try to setup up the first time and will not set it up again if it
    already exists.
    """
    test_project_name = getattr(
        request.config.option, "testprojectname", None
    )
    if test_project_name is None:
        pytest.skip(
            "project name for the test is not supplied. Please use `--testprojectname <name>` to specify one ."
        )

    test_project_directory = request.config.option.test_project_directory

    test_project_dir_full_path = os.path.join(
        test_project_directory, test_project_name
    )

    if not os.path.exists(test_project_dir_full_path):
        process = subprocess.Popen(
            ["divio", "project", "setup", test_project_name],
            cwd=test_project_directory,
        )
        stdout, stderr = process.communicate()
    return test_project_dir_full_path
