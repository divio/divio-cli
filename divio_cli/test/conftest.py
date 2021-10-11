import contextlib
import os
import pathlib
import subprocess

import pytest
import requests


@pytest.fixture(scope="session")
def _divio_project(request, tmpdir_factory):

    test_project_name = os.getenv("TEST_PROJECT_NAME", None)
    if test_project_name is None:
        pytest.skip(
            "project name for the test is not supplied. Please use $TEST_PROJECT_NAME to specify one."
        )

    # We can not use a fully randomized name as it normally would be a best
    # practice. This path needs to be well known and static as we have to
    # reference it in our test project to make docker-in-docker on Gitlab
    # work with the right volume mounts and correct paths.
    tmp_folder = pathlib.Path("test_data")

    try:
        subprocess.check_call(
            ["divio", "project", "setup", test_project_name],
            cwd=str(tmp_folder.resolve()),
        )

    except subprocess.CalledProcessError as e:
        print(e.output)
        raise
    return os.path.join(tmp_folder, test_project_name)


@pytest.fixture(scope="session")
def base_session():
    session = requests.Session()
    session.debug = False
    yield session


@pytest.fixture
def bad_request_response():
    class HttpBadResponse(object):
        ok = False
        status_code = 400
        content = "Bad response"
        text = "Bad response"

    yield HttpBadResponse()


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
