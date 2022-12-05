import contextlib
import os
import pathlib
import subprocess

import pytest
import requests


@pytest.fixture(scope="session")
def _divio_project(request, tmpdir_factory):
    test_project_name = os.getenv("TEST_PROJECT_NAME", None)
    if not test_project_name:
        pytest.skip(
            "project name for the test is not supplied. Please use $TEST_PROJECT_NAME to specify one."
        )

    # We can not use a fully randomized name as it normally would be a best
    # practice. This path needs to be well known and static as we have to
    # reference it in our test project to make docker-in-docker on Gitlab
    # work with the right volume mounts and correct paths.
    tmp_folder = pathlib.Path("test_data")
    tmp_folder.mkdir(exist_ok=True)

    subprocess.check_call(
        ["divio", "project", "setup", "--overwrite", test_project_name],
        cwd=str(tmp_folder.resolve()),
    )

    return os.path.join(tmp_folder, test_project_name)


@pytest.fixture(scope="session")
def base_session():
    session = requests.Session()
    session.debug = False
    yield session


@pytest.fixture
def bad_request_response():
    class HttpBadResponse:
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


@pytest.fixture(params=["yml", "yaml"])
def docker_compose_extension(request):
    return request.param

@pytest.fixture
def docker_compose_filename(docker_compose_extension):
    return f"docker-compose.{docker_compose_extension}"


@pytest.fixture
def divio_project(_divio_project, docker_compose_filename):
    with remember_cwd(_divio_project):
        os.rename("docker-compose.yml", docker_compose_filename)
        try:
            yield _divio_project
        finally:
            os.rename(docker_compose_filename, "docker-compose.yml")
