import contextlib
import functools
import json
import os
import subprocess
from time import time

import click
import yaml

from .. import config, settings
from ..exceptions import (
    ApplicationUUIDNotFoundException,
    ConfigurationNotFound,
    DivioException,
    DivioWarning,
    DockerComposeDoesNotExist,
)
from ..utils import check_call, check_output, is_windows


def get_project_settings_path(path=None, silent=False):
    project_home = get_application_home(path, silent=silent)

    if not project_home and silent:
        return ""

    aldryn_dot_file_path = os.path.join(project_home, settings.ALDRYN_DOT_FILE)
    divio_dot_file_path = os.path.join(project_home, settings.DIVIO_DOT_FILE)
    aldryn_dot_file_exists = os.path.exists(aldryn_dot_file_path)
    divio_dot_file_exists = os.path.exists(divio_dot_file_path)

    if aldryn_dot_file_exists:
        path = aldryn_dot_file_path

    if divio_dot_file_exists:
        path = divio_dot_file_path

    if aldryn_dot_file_exists and divio_dot_file_exists and not silent:
        click.secho(
            f"Warning: Old ({settings.ALDRYN_DOT_FILE}) and new ({settings.DIVIO_DOT_FILE}) divio configuration files found at the same time. The new one will be used.",
            fg="yellow",
        )

    if not path:
        raise ConfigurationNotFound

    return path


def get_project_settings(path=None, silent=False):
    path = get_project_settings_path(path=path, silent=silent)

    if not path and silent:
        return {}

    try:
        with open(path) as fh:
            return json.load(fh)

    except json.decoder.JSONDecodeError:
        raise DivioException(f"Unexpected value in {path}")


def migrate_project_settings(client):
    """
    Migrates old versions of `.divio/config.json` to the current format.

    Migrations:
        - legacy project-id (`id`) to application UUID (`application_uuid`)

    This function is the main entry-point for settings forward migrations.
    Place any additional migrations here.
    """

    try:
        path = get_project_settings_path(silent=True)
        settings = get_project_settings(path=path, silent=True)

    except Exception:
        # no valid settings file was found. nothing to migrate

        return

    settings_updated = False

    # legacy project id
    if "id" in settings:
        # there is already an application UUID. Nothing to do.
        if "application_uuid" in settings:
            settings.pop("id")
            settings_updated = True

        else:
            # convert legacy project id to application UUID
            with contextlib.suppress(Exception):
                settings["application_uuid"] = client.get_application_uuid(
                    application_uuid_or_remote_id=settings["id"],
                )

                settings.pop("id")
                settings_updated = True

    if settings_updated:
        with open(path, "w") as fh:
            json.dump(settings, fh, indent=4)


def get_application_home(path=None, silent=False):
    """
    find project root by traversing up the tree looking for
    the configuration file
    """
    previous_path = None
    current_path = path or os.getcwd()
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
    if silent:
        return None
    raise ConfigurationNotFound


UNIX_DOCKER_COMPOSE_FILENAME = "docker-compose.yml"
WINDOWS_DOCKER_COMPOSE_FILENAME = "docker-compose-windows.yml"


def get_docker_compose_cmd(path):
    if is_windows():
        docker_compose_filename = WINDOWS_DOCKER_COMPOSE_FILENAME
        ensure_windows_docker_compose_file_exists(path)
    else:
        docker_compose_filename = UNIX_DOCKER_COMPOSE_FILENAME

    docker_compose_filename = os.path.join(path, docker_compose_filename)

    if not os.path.isfile(docker_compose_filename):
        raise DockerComposeDoesNotExist

    conf = config.Config()
    cmd = conf.get_docker_compose_cmd()
    docker_compose_base = [*cmd, "-f", docker_compose_filename]

    def docker_compose(*commands):
        return docker_compose_base + list(commands)

    return docker_compose


def ensure_windows_docker_compose_file_exists(path):
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

    windows_path = os.path.join(path, WINDOWS_DOCKER_COMPOSE_FILENAME)
    if os.path.isfile(windows_path):
        return

    unix_path = os.path.join(path, UNIX_DOCKER_COMPOSE_FILENAME)
    if not os.path.isfile(unix_path):
        # TODO: use correct exit from click
        raise DivioException(f"docker-compose.yml not found at {unix_path}")

    with open(unix_path) as fh:
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


def get_db_container_id(path, raise_on_missing=True, prefix="DEFAULT"):
    """
    Returns the container id for a running database with a given prefix.
    """
    docker_compose = get_docker_compose_cmd(path)
    should_check_oldstyle = False
    output = None

    try:
        output = check_output(
            docker_compose("ps", "-q", f"database_{prefix}".lower()),
            catch=False,
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
            output = check_output(docker_compose("ps", "-q", "db")).rstrip(
                os.linesep
            )
        except subprocess.CalledProcessError:
            # A not existing service will result in an error.
            pass

    if not output and raise_on_missing:
        raise DivioException("Unable to find database container")
    return output


def start_database_server(docker_compose, prefix):
    start_db = time()
    click.secho(" ---> Starting local database server")
    click.secho("      ", nl=False)
    docker_compose_config = DockerComposeConfig(docker_compose)
    if f"database_{prefix}".lower() in docker_compose_config.get_services():
        check_call(docker_compose("up", "-d", f"database_{prefix}".lower()))
    else:
        check_call(docker_compose("up", "-d", "db"))
    click.secho(f"      [{int(time() - start_db)}s]")


class DockerComposeConfig:
    def __init__(self, docker_compose):
        super().__init__()
        self.config = yaml.load(
            check_output(docker_compose("config")), Loader=yaml.SafeLoader
        )

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
        return None


def allow_remote_id_override(func):
    """Adds an identifier option to the command, and gets the proper id"""

    @functools.wraps(func)
    def read_remote_id(obj, remote_id, *args, **kwargs):
        try:
            application_uuid = obj.client.get_application_uuid(
                application_uuid_or_remote_id=remote_id,
            )

        except ApplicationUUIDNotFoundException as exception:
            raise DivioException(
                "This command requires a Divio Cloud application UUID. Please "
                "provide one with the --remote-id option or call the "
                "command from an application directory."
            ) from exception

        return func(obj, application_uuid, *args, **kwargs)

    return click.option(
        "--remote-id",
        "remote_id",
        default=None,
        type=str,
        help="Remote Project ID or UUID to use for project commands. "
        "Defaults to the project in the current directory using the "
        "configuration file.",
    )(read_remote_id)


def get_service_type(identifier, path=None):
    """
    Retrieves the service type based on the `SERVICE_MANAGER` environment
    variable of a services from the docker-compose file.
    """
    project_home = get_application_home(path)
    docker_compose = get_docker_compose_cmd(project_home)

    docker_compose_config = DockerComposeConfig(docker_compose)
    services = docker_compose_config.get_services()
    if (
        identifier in services
        and "environment" in services[identifier]
        and "SERVICE_MANAGER" in services[identifier]["environment"]
    ):
        return services[identifier]["environment"]["SERVICE_MANAGER"]

    raise RuntimeError("Can not get service type")


def get_db_type(prefix, path=None):
    """
    Utility function to wrap `get_service_type` to search for databases so we
    can properly fall back to PostgreSQL in case of old structures.
    """
    db_service_name = f"database_{prefix.lower()}"
    try:
        db_type = get_service_type(db_service_name, path=path)
    except RuntimeError:
        # legacy section. we try to look for the db, if it does not exist, fail
        docker_compose = get_docker_compose_cmd(path)
        docker_compose_config = DockerComposeConfig(docker_compose)
        if not docker_compose_config.has_service("db"):
            raise DivioException(
                "The local database container must be called "
                f"`{db_service_name}`, must define the `SERVICE_MANAGER` "
                "environment variable and must mount the project directory "
                "from the host to the /app directory of the container."
                "\n\nSee https://docs.divio.com/en/latest/reference/docker-docker-compose/#database-default",
            )
        # Fall back to database for legacy docker-compose files
        db_type = "fsm-postgres"
    return db_type


class MainStep:
    def __init__(self, name):
        click.secho(f" ===> {name} ")
        self.start = time()

    def done(self):
        click.secho("Done", fg="green", nl=False)
        click.echo(f" [{int(time() - self.start)}s]")


def step(message, **kwargs):
    click.secho(f" ---> {message} ", **kwargs)


class TimedStep:
    def __init__(self, message):
        self.start = time()
        step(message, nl=False)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, _exc_tb):
        if not exc_type:
            self.done()

        if isinstance(exc, DivioException):
            # Since inside a step, ensure we have the right formatting
            prefix = "error!"
            if isinstance(exc, DivioWarning):
                prefix = "warning!"
            exc.message = f" {prefix}\n{exc.message or ''}"

    def done(self):
        click.echo(f" [{int(time() - self.start)}s]")
