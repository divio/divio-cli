import os

import click


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
        if os.path.exists(os.path.join(current_path, '.aldryn')):
            return current_path

        # traversing up the tree
        previous_path = current_path
        current_path = os.path.abspath(os.path.join(current_path, os.pardir))

    raise click.ClickException(
        "Aldryn project file '.aldryn' could not be found! Please make sure "
        "you're in an Aldryn project folder and the file exists."
    )
