import os
import subprocess

import click
import pytest


@pytest.fixture(scope="session")
def divio_project(request, tmpdir_factory):

    test_project_name = os.getenv("TEST_PROJECT_NAME", None)
    if test_project_name is None:
        pytest.skip(
            "project name for the test is not supplied. Please use $TEST_PROJECT_NAME to specify one."
        )

    tmp_folder = tmpdir_factory.mktemp("data")
    process = subprocess.Popen(
        ["divio", "project", "setup", test_project_name],
        cwd=str(tmp_folder),
    )
    stdout, stderr = process.communicate()
    click.echo(stdout)
    click.echo(stderr, err=True)
    return os.path.join(tmp_folder, test_project_name)
