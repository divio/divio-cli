import contextlib
import os
import subprocess

import pytest


@pytest.fixture(scope="session")
def _divio_project(request, tmpdir_factory):

    test_project_name = os.getenv("TEST_PROJECT_NAME", None)
    if test_project_name is None:
        pytest.skip(
            "project name for the test is not supplied. Please use $TEST_PROJECT_NAME to specify one."
        )

    tmp_folder = tmpdir_factory.mktemp("data")
    subprocess.call(
        ["divio", "project", "setup", test_project_name],
        cwd=str(tmp_folder),
    )
    return os.path.join(tmp_folder, test_project_name)


@contextlib.contextmanager
def remember_cwd(targetdir):
    curdir = os.getcwd()
    try:
        os.chdir(targetdir)
        yield
    finally:
        os.chdir(curdir)


@pytest.fixture
def divio_project(_divio_project):
    with remember_cwd(_divio_project):
        yield _divio_project
