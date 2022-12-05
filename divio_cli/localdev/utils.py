import functools
import json
import os
import subprocess
import sys
from time import time

from attr import define, field
import click
import yaml

from .. import config, exceptions, settings
from ..utils import check_call, check_output, is_windows


DOT_ALDRYN_FILE_NOT_FOUND = (
    "Divio Cloud configuration file '{}' or '{}' could not be found!\n"
    "Please make sure you're in a Divio Cloud project folder and the "
    "file exists.\n\n"
    "You can create a new configuration file for an existing project "
    "with the `divio app configure` command.".format(
        settings.ALDRYN_DOT_FILE, settings.DIVIO_DOT_FILE
    )
)


def get_project_settings(project_home):
    try:
        old_file_found = False
        if os.path.exists(
            os.path.join(project_home, settings.ALDRYN_DOT_FILE)
        ):
            path = os.path.join(project_home, settings.ALDRYN_DOT_FILE)
            old_file_found = True

        if os.path.exists(os.path.join(project_home, settings.DIVIO_DOT_FILE)):
            path = os.path.join(project_home, settings.DIVIO_DOT_FILE)
            if old_file_found:
                click.secho(
                    "Warning: Old ({}) and new ({}) divio configuration files found at the same time. The new one will be used.".format(
                        settings.ALDRYN_DOT_FILE, settings.DIVIO_DOT_FILE
                    ),
                    fg="yellow",
                )

        with open(path) as fh:
            return json.load(fh)
    except (TypeError, OSError):
        raise click.ClickException(DOT_ALDRYN_FILE_NOT_FOUND)
    except json.decoder.JSONDecodeError:
        click.secho("Error: Unexpected value in {}".format(path), fg="red")
        sys.exit(1)


def get_application_home(path):
    """
    find project root by traversing up the tree looking for
    the configuration file
    """
    previous_path = None
    current_path = path
    global_config_path = config.get_global_config_path()

    # loop until we're at the root of the volume
    while current_path != previous_path:
        # check if configuration file exists in current directory
        dotfile = os.path.join(current_path, settings.ALDRYN_DOT_FILE)
        if os.path.exists(dotfile) and dotfile != global_config_path:
            return current_path

        # check if configuration file exists in current directory
        dotfile = os.path.join(current_path, settings.DIVIO_DOT_FILE)
        if os.path.exists(dotfile) and dotfile != global_config_path:
            return current_path

        # traversing up the tree
        previous_path = current_path
        current_path = os.path.abspath(os.path.join(current_path, os.pardir))

    raise click.ClickException(DOT_ALDRYN_FILE_NOT_FOUND)


UNIX_DOCKER_COMPOSE_FILENAMES = [
    "docker-compose.yml",
    "docker-compose.yaml",
]
WINDOWS_DOCKER_COMPOSE_FILENAMES = [
    "docker-compose-windows.yml",
    "docker-compose-windows.yaml",
]


def get_docker_compose_filename(path):
    if is_windows():
        docker_compose_filenames = WINDOWS_DOCKER_COMPOSE_FILENAMES
        get_windows_docker_compose_file(path)
    else:
        docker_compose_filenames = UNIX_DOCKER_COMPOSE_FILENAMES

    for filename in docker_compose_filenames:
        docker_compose_filename = os.path.join(path, filename)
        if os.path.isfile(docker_compose_filename):
            return docker_compose_filename

    raise RuntimeError("Warning: Could not find a 'docker-compose.yml' file.")


def get_docker_compose_cmd(path):
    docker_compose_filename = get_docker_compose_filename(path)

    conf = config.Config()
    cmd = conf.get_docker_compose_cmd()
    docker_compose_base = cmd + ["-f", docker_compose_filename]

    def docker_compose(*commands):
        return docker_compose_base + [cmd for cmd in commands]

    return docker_compose


def get_windows_docker_compose_file(path):
    """
    Unfortunately, docker-compose is not yet officially released
     for Windows There's still some rough edges, and volume
     configuration is one. There's also some open issues in
     boot2docker for windows which makes things difficult.

    We have to change the volume specifications to a very specific
     format:

     - absolute paths: relative one's are not yet supported
     - currently only works if the project is running on the C:\\ drive
     - unix style paths: need to replace '\' with '/'
     - paths have to start with /c/ instead of C:\\ otherwise
        docker-compose gets confused because they use : as separation

    Example:
      unix format:  .:/app:rw
      cwd:          C:\\Users\\aldryn\\acme-portfolio
      windows:     /c/Users/aldryn/acme-portfolio:/app:rw

    Hope that's all. And of course, I'm sorry.
    """

    for filename in WINDOWS_DOCKER_COMPOSE_FILENAMES:
        windows_path = os.path.join(path, filename)
        if os.path.isfile(windows_path):
            return windows_path

    for filename in UNIX_DOCKER_COMPOSE_FILENAMES:
        unix_path = os.path.join(path, filename)
        if os.path.isfile(unix_path):
            windows_filename = WINDOWS_DOCKER_COMPOSE_FILENAMES[0]
            windows_filename = (
                os.path.splitext(windows_filename)[0]
                + os.path.splitext(filename)[1]
            )
            windows_path = os.path.join(path, windows_filename)
            break
    else:
        raise RuntimeError(
            "Warning: Could not find a 'docker-compose.yml' file."
        )

    with open(unix_path, "r") as fh:
        conf = yaml.load(fh, Loader=yaml.SafeLoader)

    for component, sections in conf.items():
        if "volumes" not in sections:
            continue
        volumes = []
        for volume in sections["volumes"]:
            parts = volume.split(":")
            if len(parts) == 2:
                old_host, container = parts
                mode = None
            else:
                old_host, container, mode = parts

            # assuming relative path's for old_host
            new_host = os.path.abspath(os.path.join(path, old_host))
            # replace C:\ with /c/, because, docker on windows
            new_host = new_host.replace("C:\\", "/c/")
            # change to unix paths
            new_host = new_host.replace("\\", "/")
            new_volume = [new_host, container]
            if mode:
                new_volume.append(mode)
            volumes.append(":".join(new_volume))

        conf[component]["volumes"] = volumes

    with open(windows_path, "w+") as fh:
        yaml.safe_dump(conf, fh)


def get_db_container_id(context, raise_on_missing=True, prefix="DEFAULT"):
    """
    Returns the container id for a running database with a given prefix.
    """
    should_check_oldstyle = False
    output = None

    try:
        output = context.docker_compose(
            "ps",
            "-q",
            "database_{}".format(prefix).lower(),
            catch=False,
            capture=True,
            stderr=open(os.devnull, "w"),
        ).rstrip(os.linesep)
        if not output:
            # This behavior was briefly used in docker-compose v2.
            # The output can be empty if the container does not exist.
            # For information: https://github.com/docker/compose-cli/issues/1893
            should_check_oldstyle = True
    except subprocess.CalledProcessError:
        # A not existing service will result in an error.
        should_check_oldstyle = True

    if should_check_oldstyle:
        try:
            output = context.docker_compose(
                "ps", "-q", "db", capture=True
            ).rstrip(os.linesep)
        except subprocess.CalledProcessError:
            # A not existing service will result in an error.
            pass

    if not output and raise_on_missing:
        raise exceptions.DivioException("Unable to find database container")
    return output


def start_database_server(context, prefix):
    start_db = time()
    click.secho(" ---> Starting local database server")
    click.secho("      ", nl=False)
    if (
        "database_{}".format(prefix).lower()
        in context.docker_compose_config.get_services()
    ):
        context.docker_compose(
            "up", "-d", "database_{}".format(prefix).lower()
        )
    else:
        context.docker_compose("up", "-d", "db")
    click.secho("      [{}s]".format(int(time() - start_db)))


@define
class DockerComposeConfig:
    config = field()

    @classmethod
    def load_from_yaml(cls, config):
        return cls(config=yaml.load(config, Loader=yaml.SafeLoader))

    def get_services(self):
        return self.config.get("services", {})

    def has_service(self, service):
        return service in self.get_services().keys()

    def has_volume_mount(self, service, remote_path):
        """
        Services may look like the following depending on the OS:

        - /home/user/some/path:/app:rw
        - C:\\whatever\\windows\\path:/app:rw (windows)
        """
        try:
            service_config = self.get_services()[service]
        except KeyError:
            return False

        for mount in service_config.get("volumes", []):
            # docker compose < 2
            if not isinstance(mount, dict):
                bits = mount.strip().split(":")
                if len(bits) > 2 and bits[-2] == remote_path:
                    return True
            else:
                if mount["target"] == remote_path:
                    return True


def get_service_type(context, identifier):
    """
    Retrieves the service type based on the `SERVICE_MANAGER` environment
    variable of a services from the docker-compose file.
    """
    services = context.docker_compose_config.get_services()
    if (
        identifier in services
        and "environment" in services[identifier]
        and "SERVICE_MANAGER" in services[identifier]["environment"]
    ):
        return services[identifier]["environment"]["SERVICE_MANAGER"]

    raise RuntimeError("Can not get service type")


def get_db_type(context, prefix):
    """
    Utility function to wrap `get_service_type` to search for databases so we
    can properly fall back to PostgreSQL in case of old structures.
    """
    try:
        db_type = get_service_type(
            context, "database_{}".format(prefix.lower())
        )
    except RuntimeError:
        if not context.docker_compose_config.has_service("db"):
            click.secho(
                "The local database container must be called "
                "`database_default`, must define the `SERVICE_MANAGER` "
                "environment variable and must mount the project directory "
                "from the host to the /app directory of the container."
                "\n\nSee https://docs.divio.com/en/latest/reference/docker-docker-compose/#database-default",
                fg="red",
            )
            sys.exit(1)
        else:
            # Fall back to database for legacy docker-compose files
            db_type = "fsm-postgres"
    return db_type
