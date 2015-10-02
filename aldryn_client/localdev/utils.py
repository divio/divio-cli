import json
import os

import click

from .. import settings


def get_aldryn_project_settings(path):
    project_home = get_project_home(path)
    with open(os.path.join(project_home, settings.ALDRYN_DOT_FILE)) as fh:
        return json.load(fh)


def get_project_home(path=None):
    """
    find project root by traversing up the tree looking for
    the '.aldryn' file
    """
    previous_path = None
    current_path = path or os.getcwd()

    # loop until we're at the root of the volume
    while current_path != previous_path:

        # check if '.aldryn' file exists in current directory
        dotfile = os.path.join(current_path, settings.ALDRYN_DOT_FILE)
        if os.path.exists(dotfile):
            return current_path

        # traversing up the tree
        previous_path = current_path
        current_path = os.path.abspath(os.path.join(current_path, os.pardir))

    raise click.ClickException(
        "Aldryn project file '.aldryn' could not be found! Please make sure "
        "you're in an Aldryn project folder and the file exists."
    )
