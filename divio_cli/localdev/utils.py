import json
import os
import sys
from time import time

import click
import yaml

from .. import config, exceptions, settings
from ..utils import check_call, check_output, is_windows

DOT_ALDRYN_FILE_NOT_FOUND = (
    "Divio Cloud project file '.aldryn' could not be found!\n"
    "Please make sure you're in a Divio Cloud project folder and the "
    "file exists."
)


def get_aldryn_project_settings(path=None, silent=False):
    project_home = get_project_home(path, silent=silent)
    try:
        with open(os.path.join(project_home, settings.ALDRYN_DOT_FILE)) as fh:
            return json.load(fh)
    except (TypeError, OSError):
        raise click.ClickException(DOT_ALDRYN_FILE_NOT_FOUND)


def get_project_home(path=None, silent=False):
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
        if os.path.exists(dotfile) and dotfile != config.CONFIG_FILE_PATH:
            return current_path

        # traversing up the tree
        previous_path = current_path
        current_path = os.path.abspath(os.path.join(current_path, os.pardir))
    if silent:
        return
    raise click.ClickException(DOT_ALDRYN_FILE_NOT_FOUND)


UNIX_DOCKER_COMPOSE_FILENAME = "docker-compose.yml"
WINDOWS_DOCKER_COMPOSE_FILENAME = "docker-compose-windows.yml"


def get_docker_compose_cmd(path):
    if is_windows():
        docker_compose_filename = WINDOWS_DOCKER_COMPOSE_FILENAME
        ensure_windows_docker_compose_file_exists(path)
    else:
        docker_compose_filename = UNIX_DOCKER_COMPOSE_FILENAME

    docker_compose_base = [
        "docker-compose",
        "-f",
        os.path.join(path, docker_compose_filename),
    ]

    def docker_compose(*commands):
        return docker_compose_base + [cmd for cmd in commands]

    return docker_compose


def prepare_yaml_for_windows(conf):
    """
    We have to make two changes for postgres on windows:

    1) remove PGDATA environment variable
    2) switch the postgres data volume to an anonymous volume

    Both changes exist to prevent permission issues.

    """
    for component, containers in conf.items():
        if component == "services":

            for container_name, container in containers.items():

                if "environment" in container and "PGDATA" in container["environment"]:
                    del container["environment"]["PGDATA"]

                if "volumes" in container:
                    volumes = []
                    for volume in container["volumes"]:
                        if "/var/lib/postgresql/data" in volume:
                            # due to permission issues, we just use an
                            # anonymous volume on windows for the database
                            volumes.append("/var/lib/postgresql/data")
                        else:
                            volumes.append(volume)

                    conf[component][container_name]["volumes"] = volumes
    return conf

def ensure_windows_docker_compose_file_exists(path):
    windows_path = os.path.join(path, WINDOWS_DOCKER_COMPOSE_FILENAME)
    if os.path.isfile(windows_path):
        return

    unix_path = os.path.join(path, UNIX_DOCKER_COMPOSE_FILENAME)
    if not os.path.isfile(unix_path):
        # TODO: use correct exit from click
        click.secho(
            "docker-compose.yml not found at {}".format(unix_path), fg="red"
        )
        sys.exit(1)

    with open(unix_path, "r") as fh:
        conf = yaml.load(fh)

    windows_conf = prepare_yaml_for_windows(conf)

    with open(windows_path, "w+") as fh:
        yaml.safe_dump(windows_conf, fh)



def get_db_container_id(path, raise_on_missing=True):
    docker_compose = get_docker_compose_cmd(path)
    output = check_output(docker_compose("ps", "-q", "db")).rstrip(os.linesep)
    if not output and raise_on_missing:
        raise exceptions.AldrynException("Unable to find database container")
    return output


def start_database_server(docker_compose):
    start_db = time()
    click.secho(" ---> Starting local database server")
    click.secho("      ", nl=False)
    check_call(docker_compose("up", "-d", "db"))
    click.secho("      [{}s]".format(int(time() - start_db)))


class DockerComposeConfig(object):
    def __init__(self, docker_compose):
        super(DockerComposeConfig, self).__init__()
        self.config = yaml.load(check_output(docker_compose("config")))

    def get_services(self):
        return self.config.get("services", {})

    def has_service(self, service):
        return service in self.get_services().keys()

    def has_volume_mount(self, service, remote_path):
        """
        Services may look like the following depending on the OS:

        - /home/user/some/path:/app:rw
        - C:\whatever\windows\path:/app:rw (windows)
        """
        try:
            service_config = self.get_services()[service]
        except KeyError:
            return False

        for mount in service_config.get("volumes", []):
            bits = mount.strip().split(":")
            if len(bits) > 2 and bits[-2] == remote_path:
                return True


def allow_remote_id_override(func):
    """Adds an identifier option to the command, and gets the proper id"""

    def read_remote_id(remote_id, *args, **kwargs):
        ERROR_MSG = (
            "This command requires a Divio Cloud Project id. Please "
            "provide one with the --remote-id option or call the "
            "command from a project directory (with a .aldryn file)."
        )

        if not remote_id:
            try:
                remote_id = get_aldryn_project_settings(silent=True)["id"]
            except KeyError:
                raise click.ClickException(ERROR_MSG)
            else:
                if not remote_id:
                    raise click.ClickException(ERROR_MSG)
        return func(remote_id, *args, **kwargs)

    return click.option(
        "--remote-id",
        "remote_id",
        default=None,
        type=int,
        help="Remote Project ID to use for project commands. "
        "Defaults to the project in the current directory using the "
        ".aldryn file.",
    )(read_remote_id)
