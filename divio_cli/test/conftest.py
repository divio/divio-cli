import contextlib
import os
import shlex
import shutil
import subprocess
from unittest.mock import Mock

import pytest
import requests


TEST_DATA_DIRECTORY = "test_data"


@pytest.fixture(scope="session")
def _divio_project(request, pytestconfig, tmpdir_factory):  # noqa: PT005
    capturemanager = pytestconfig.pluginmanager.getplugin("capturemanager")

    # check if test project is set
    test_project_name = os.getenv("TEST_PROJECT_NAME", "")

    if not test_project_name:
        pytest.skip(
            "project name for the test is not supplied. Please use $TEST_PROJECT_NAME to specify one."
        )

    # create test data directory if not present
    if not os.path.exists(TEST_DATA_DIRECTORY):
        os.makedirs(TEST_DATA_DIRECTORY)

    # setup divio project
    try:
        # disable stdout capturing
        capturemanager.suspend_global_capture(in_=True)

        print("\n=== divio project setup ===")  # noqa: T201

        # We can not use a fully randomized name as it normally would be a best
        # practice. This path needs to be well known and static as we have to
        # reference it in our test project to make docker-in-docker on Gitlab
        # work with the right volume mounts and correct paths.
        test_project_directory = os.path.join(
            TEST_DATA_DIRECTORY, test_project_name
        )

        # Locally, we may run the tests multiple times
        if os.path.exists(test_project_directory):
            # Reuse the existing project
            if os.getenv("TEST_KEEP_PROJECT", "0") == "1":
                print("TEST_KEEP_PROJECT is set. skipping setup")  # noqa: T201

                return test_project_directory

            # Cleanup
            print(f"removing {test_project_directory}")  # noqa: T201

            shutil.rmtree(test_project_directory)

        # setup
        setup_command = f"divio app setup {test_project_name}"
        env = os.environ.copy()

        if "TEST_ZONE" in env:
            env["DIVIO_ZONE"] = env["TEST_ZONE"]

        print(f"setup command: {setup_command}")  # noqa: T201

        subprocess.check_call(
            shlex.split(setup_command),
            env=env,
            cwd=TEST_DATA_DIRECTORY,
        )

        return test_project_directory

    finally:
        print("=== divio project setup finished ===")  # noqa: T201

        capturemanager.resume_global_capture()


@pytest.fixture(scope="session")
def base_session():
    session = requests.Session()
    session.debug = False
    return session


@pytest.fixture()
def bad_request_response():
    class HttpBadResponse:
        ok = False
        status_code = 400
        content = "Bad response"
        text = "Bad response"

    return HttpBadResponse()


@contextlib.contextmanager
def remember_cwd(targetdir):
    curdir = os.getcwd()
    try:
        os.chdir(targetdir)
        yield
    finally:
        os.chdir(curdir)


@pytest.fixture()
def divio_project(_divio_project):
    with remember_cwd(_divio_project):
        yield _divio_project


@pytest.fixture(autouse=True)
def _sleepless(monkeypatch):
    # IMPORTANT: this only works if we use "import time"
    # vs "from time import sleep" in the module
    # under test
    monkeypatch.setattr("time.sleep", Mock())
