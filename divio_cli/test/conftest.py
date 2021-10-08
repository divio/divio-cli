import contextlib
import os
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

    tmp_folder = tmpdir_factory.mktemp("data")
    try:
        subprocess.check_call(
            ["divio", "project", "setup", test_project_name],
            cwd=str(tmp_folder),
        )
    except subprocess.CalledProcessError as e:
        print(e.output)
        import pathlib

        p = pathlib.Path(tmp_folder)
        print(list(p.rglob("*")))
        print("*"*100)
        r = subprocess.run(["docker-comppse", "run", "db", "ls", "-la", "/app"])
        print(r.stdout)
        print(r.stderr)
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
