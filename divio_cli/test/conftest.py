import os
import subprocess

import click
import pytest


@pytest.fixture(scope="session")
def divio_project(request):

    test_project_name = os.getenv("TEST_PROJECT_NAME", None)
    if test_project_name is None:
        pytest.skip(
            "project name for the test is not supplied. Please use $TEST_PROJECT_NAME to specify one."
        )

    from tempfile import TemporaryDirectory

    with TemporaryDirectory() as tmp_folder:
        process = subprocess.Popen(
            ["divio", "project", "setup", test_project_name],
            cwd=tmp_folder,
        )
        stdout, stderr = process.communicate()
        click.echo(stdout)
        click.echo(stderr)
        yield os.path.join(tmp_folder, test_project_name)
