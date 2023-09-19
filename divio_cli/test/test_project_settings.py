import json
import os
import subprocess
from tempfile import TemporaryDirectory

import pytest

from divio_cli.settings import DIVIO_DOT_FILE


@pytest.mark.integration()
def test_migrate_project_id_to_application_uuid():
    with TemporaryDirectory() as project_home:
        divio_dot_file = os.path.join(project_home, DIVIO_DOT_FILE)

        # create legacy project settings
        os.makedirs(os.path.dirname(divio_dot_file))

        with open(divio_dot_file, "w+") as fh:
            json.dump(
                {
                    "id": int(os.environ.get("TEST_PROJECT_ID")),
                    "zone": os.environ.get("TEST_ZONE"),
                },
                fh,
            )

        # migrate project settings
        # project settings migration gets run on the fly by any sub command
        # "divio app -h" was chosen by fair dice roll
        subprocess.check_call(
            ["divio", "app", "-h"],
            cwd=project_home,
        )

        # check if the legacy project id was translated to an application UUID
        settings = json.load(open(divio_dot_file))

        assert "id" not in settings
        assert settings["application_uuid"] == os.environ["TEST_PROJECT_UUID"]
