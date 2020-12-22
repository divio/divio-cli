import errno
import os
import subprocess

import pytest


@pytest.fixture(scope="session")
def divio_project(request):

    test_project_name = os.getenv("TEST_PROJECT_NAME", None)
    if test_project_name is None:
        pytest.skip(
            "project name for the test is not supplied. Please use $TEST_PROJECT_NAME to specify one."
        )

    test_project_dir_full_path = os.path.join("workspace", test_project_name)

    if not os.path.exists(test_project_dir_full_path):
        try:
            os.makedirs("workspace")
        except OSError as exc:
            if exc.errno == errno.EEXIST and os.path.isdir("workspace"):
                pass
            else:
                raise

        process = subprocess.Popen(
            ["divio", "project", "setup", test_project_name],
            cwd="workspace",
        )
        stdout, stderr = process.communicate()
    return test_project_dir_full_path
