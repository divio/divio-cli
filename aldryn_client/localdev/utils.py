import json
import sys
import os

import click
import yaml

from ..utils import check_output, is_windows
from .. import settings


def get_aldryn_project_settings(path=None):
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


UNIX_DOCKER_COMPOSE_FILENAME = 'docker-compose.yml'
WINDOWS_DOCKER_COMPOSE_FILENAME = 'docker-compose-windows.yml'


def get_docker_compose_cmd(path):
    if is_windows():
        docker_compose_filename = WINDOWS_DOCKER_COMPOSE_FILENAME
        ensure_windows_docker_compose_file_exists(path)
    else:
        docker_compose_filename = UNIX_DOCKER_COMPOSE_FILENAME

    docker_compose_base = [
        'docker-compose', '-f', os.path.join(path, docker_compose_filename)
    ]

    def docker_compose(*commands):
        return docker_compose_base + [cmd for cmd in commands]

    return docker_compose


def ensure_windows_docker_compose_file_exists(path):
    """ I'm sorry """
    windows_path = os.path.join(path, WINDOWS_DOCKER_COMPOSE_FILENAME)
    if os.path.isfile(windows_path):
        return

    unix_path = os.path.join(path, UNIX_DOCKER_COMPOSE_FILENAME)
    if not os.path.isfile(unix_path):
        exit('docker-compose.yml not found')

    with open(unix_path, 'r') as fh:
        config = yaml.load(fh)

    for component, sections in config.iteritems():
            if 'volumes' not in sections:
                continue
            volumes = []
            for volume in sections['volumes']:
                parts = volume.split(':')
                if len(parts) == 2:
                    old_host, container = parts
                    mode = None
                else:
                    old_host, container, mode = parts

                # assuming relative path's for old_host
                new_host = os.path.abspath(os.path.join(path, old_host))
                # replace C:\ with /c/, because, docker on windows
                new_host = new_host.replace('C:\\', '/c/')
                # change to unix paths
                new_host = new_host.replace('\\', '/')
                new_volume = [new_host, container]
                if mode:
                    new_volume.append(mode)
                volumes.append(':'.join(new_volume))

            config[component]['volumes'] = volumes

    with open(windows_path, 'w+') as fh:
        yaml.dump(config, fh)


def get_db_container_id(path):
    docker_compose = get_docker_compose_cmd(path)
    output = check_output(docker_compose('ps', '-q', 'db'))
    return output.replace(os.linesep, '')
