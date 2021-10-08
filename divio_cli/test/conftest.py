import contextlib
import os
import subprocess

import pytest
import requests

import pathlib


@pytest.fixture(scope="session")
def _divio_project(request, tmpdir_factory):

    test_project_name = os.getenv("TEST_PROJECT_NAME", None)
    if test_project_name is None:
        pytest.skip(
            "project name for the test is not supplied. Please use $TEST_PROJECT_NAME to specify one."
        )

    #tmp_folder = tmpdir_factory.mktemp("data")
    tmp_folder = pathlib.Path("test_data")

    try:
        subprocess.check_call(
            ["divio", "project", "setup", test_project_name],
            cwd=str(tmp_folder.resolve()),
        )

# this temp folder should get injected into the docker-compose file OR we make the docker compose call allow for a dynamic mount 
# the tmp dir must be in the project dir, otherwise the mounts will not work


    except subprocess.CalledProcessError as e:
        print(e.output)

        p = pathlib.Path(tmp_folder)
        print(list(p.rglob("*")))
        print("*"*100)
        r = subprocess.run(["docker-compose", "--log-level", "DEBUG", "run", "db", "ls", "-la", "/app"],cwd=os.path.join(str(tmp_folder), test_project_name))
        print(r.stdout)
        print(r.stderr)
        r = subprocess.run(["docker-compose", "run", "db", "pwd"],cwd=os.path.join(str(tmp_folder), test_project_name))
        print(r.stdout)
        print(r.stderr)
        r = subprocess.run(["docker-compose", "run", "db", "mount"],cwd=os.path.join(str(tmp_folder), test_project_name))
        print(r.stdout)
        print(r.stderr)
        r = subprocess.run(["docker-compose", "run", "web", "mount"],cwd=os.path.join(str(tmp_folder), test_project_name))
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
