import errno
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
from pathlib import PurePosixPath
from time import sleep, time

import click
import requests

from divio_cli.exceptions import (
    ConfigurationNotFound,
    DivioException,
    DockerComposeDoesNotExist,
    ExitCode,
)
from divio_cli.localdev.push import PushDb, PushMedia, dump_database
from divio_cli.utils import get_local_git_remotes

from .. import settings
from ..cloud import get_divio_zone
from ..utils import (
    check_call,
    check_output,
    download_file,
    get_subprocess_env,
    is_windows,
    launch_url,
    needs_legacy_migration,
)
from . import backups, utils
from .utils import get_application_home, get_project_settings


DEFAULT_GIT_HOST = "git@git.{divio_zone}"
GIT_CLONE_URL = "{git_host}:{project_slug}.git"


DEFAULT_DUMP_FILENAME = "local_db.sql"
DEFAULT_SERVICE_PREFIX = "DEFAULT"


def get_git_host(zone=None):
    try:
        git_host = get_project_settings(get_application_home()).get(
            "git_host", None
        )
    except ConfigurationNotFound:
        git_host = None

    if not git_host:
        git_host = os.environ.get("DIVIO_GIT_HOST")

    if git_host:
        click.secho(f"Using custom git host {git_host}\n", fg="yellow")
    else:
        if not zone:
            zone = get_divio_zone()
        git_host = DEFAULT_GIT_HOST.format(divio_zone=zone)
    return git_host


def get_git_clone_url(slug, application_uuid, client, zone=None):
    remote_dsn = client.get_repository_dsn(application_uuid)
    # if we could get a remote_dsn, us it! Otherwise, its probably a default git setup
    if remote_dsn:
        return remote_dsn
    # TODO: mirrors should fail here
    return GIT_CLONE_URL.format(
        git_host=get_git_host(zone=zone), project_slug=slug
    )


def clone_project(website_slug, path, client, zone=None, branch=None):
    click.secho("\ncloning project repository", fg="green")
    application_uuid = client.get_application_uuid_for_slug(website_slug)

    website_git_url = get_git_clone_url(
        website_slug, application_uuid, client=client, zone=zone
    )
    clone_args = ["git", "clone"]
    if branch:
        clone_args.append(f"-b{branch}")
    clone_args.append(website_git_url)
    if path:
        clone_args.append(path)

    check_call(clone_args)


def configure_project(website_slug, path, client, zone=None):
    application_uuid = client.get_application_uuid_for_slug(website_slug)

    if not zone:
        zone = get_divio_zone()

    # create configuration file
    website_data = {
        "application_uuid": application_uuid,
        "id": application_uuid,
        "slug": website_slug,
        "zone": zone,
    }
    if os.path.exists(os.path.join(path, settings.ALDRYN_DOT_FILE)):
        path = os.path.join(path, settings.ALDRYN_DOT_FILE)
    else:
        path = os.path.join(path, settings.DIVIO_DOT_FILE)

    # Create folders if they don't exist yet.
    if not os.path.exists(os.path.dirname(path)):
        try:
            os.makedirs(os.path.dirname(path))
        except OSError as exc:  # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise

    if not os.path.isdir(os.path.dirname(path)):
        raise DivioException(f"{os.path.dirname(path)} is not a directory")

    # Write the file
    with open(path, "w+") as fh:
        json.dump(website_data, fh, indent=4)

    click.secho(
        "Configuration file: {}".format(click.style(path, fg="bright_green"))
    )
    click.secho(
        "Git remote:         {}".format(
            click.style(
                get_git_clone_url(
                    website_slug, application_uuid, client, zone=zone
                ),
                fg="bright_green",
            )
        )
    )


def setup_website_containers(
    client, application_uuid, environment, path, prefix=DEFAULT_SERVICE_PREFIX
):
    try:
        docker_compose = utils.get_docker_compose_cmd(path)
    except DockerComposeDoesNotExist as e:
        # give a reason
        raise DockerComposeDoesNotExist("Cannot setup containers") from e
    docker_compose_config = utils.DockerComposeConfig(docker_compose)

    # stop all running containers for project
    check_call(docker_compose("stop"))

    # pull docker images
    click.secho("downloading remote docker images", fg="green")
    check_call(docker_compose("pull"))

    # build docker images
    click.secho("building local docker images", fg="green")
    check_call(docker_compose("build"))

    if docker_compose_config.has_service(
        "db"
    ) or docker_compose_config.has_service(f"database_{prefix}".lower()):
        click.secho("removing old database container", fg="green")
        if docker_compose_config.has_service("database_default"):
            check_call(docker_compose("stop", "database_default"), catch=False)
            check_call(
                docker_compose("rm", "-f", "database_default"), catch=False
            )
        else:
            check_call(docker_compose("stop", "db"))
            check_call(docker_compose("rm", "-f", "db"))
        click.secho("creating new database container", fg="green")

        db_type = utils.get_db_type(prefix, path=path)

        application_home = utils.get_application_home(path)
        dump_path = os.path.join(application_home, settings.DIVIO_DUMP_FOLDER)

        ImportRemoteDatabase(
            client=client,
            application_uuid=application_uuid,
            environment=environment,
            path=path,
            prefix=prefix,
            db_type=db_type,
            dump_path=dump_path,
        )()

        if needs_legacy_migration():
            click.secho("syncing and migrating database", fg="green")
            if is_windows():
                # interactive mode is not yet supported with docker-compose
                # on windows. that's why we have to call it as daemon
                # and just wait a sane time
                check_call(
                    docker_compose("run", "-d", "web", "start", "migrate"),
                )
                sleep(30)
            else:
                check_call(
                    docker_compose(
                        "run",
                        "web",
                        "/bin/bash",
                        "-c",
                        "sleep 5; start migrate",
                    ),
                )


def create_workspace(
    client,
    website_slug,
    environment,
    path=None,
    force_overwrite=False,
    zone=None,
):
    click.secho("Creating workspace", fg="green")

    path = os.path.abspath(
        os.path.join(path, website_slug) if path else website_slug
    )

    if os.path.exists(path) and (not os.path.isdir(path) or os.listdir(path)):
        if force_overwrite or click.confirm(
            f"The path {path} already exists and is not an empty directory. "
            "Do you want to remove it and continue?"
        ):
            if os.path.isdir(path):

                def del_rw(action, name, exc):
                    os.chmod(name, stat.S_IWRITE)
                    os.remove(name)

                shutil.rmtree(path, onerror=del_rw)
            else:
                os.remove(path)
        else:
            raise DivioException("Aborting", fg=None)

    application_uuid = client.get_application_uuid_for_slug(website_slug)
    env = client.get_environment_by_application(application_uuid, environment)

    # clone git project
    clone_project(
        website_slug=website_slug,
        path=path,
        client=client,
        zone=zone,
        branch=env["branch"],
    )

    # check for new baseproject + add configuration file
    configure_project(
        website_slug=website_slug, path=path, client=client, zone=zone
    )

    # setup docker website containers (if docker-compose.yml exists)
    try:
        setup_website_containers(
            client=client,
            application_uuid=application_uuid,
            environment=environment,
            path=path,
        )
        pull_media(client=client, environment=environment, path=path)
    except DockerComposeDoesNotExist:
        click.secho(
            "Warning: docker-compose.yml does not exist. Will continue without...",
            fg="yellow",
        )

    instructions = (
        "Your workspace is setup and ready to start.",
        f"Change directory to '{path}' and run 'divio app up'",
    )

    click.secho(f"\n\n{os.linesep.join(instructions)}", fg="green")


class DatabaseImportBase:
    restore_commands = {
        "fsm-postgres": {
            "sql": "psql -U postgres db < {}",
            "binary": (
                "pg_restore -U postgres --dbname=db -n public "
                "--no-owner --exit-on-error {}"
            ),
            "archived-binary": (
                "tar -xzOf {}"
                " | pg_restore -U postgres --dbname=db -n public "
                "--no-owner --exit-on-error"
            ),
        },
        "fsm-mysql": {
            "sql": "mysql db < {}",
            "binary": "mysql db --binary-mode=1 < {}",
            "archived-binary": "tar -xzOf {}| mysql db --binary-mode=1",
        },
    }

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.client = kwargs.pop("client")
        self.prefix = kwargs.pop("prefix")
        self.db_type = kwargs.pop("db_type")

        self.path = kwargs.pop("path", None) or utils.get_application_home()
        self.dump_path = kwargs.pop("dump_path", None) or self.path
        self.application_uuid = utils.get_project_settings(self.path)[
            "application_uuid"
        ]
        self.website_slug = utils.get_project_settings(self.path)["slug"]
        try:
            self.docker_compose = utils.get_docker_compose_cmd(self.path)
        except DockerComposeDoesNotExist:
            self.docker_compose = None
        self.database_extensions = self.get_active_db_extensions()
        self.start_time = time()

    def __call__(self, *args, **kwargs):
        return self.run()

    def setup(self):
        raise NotImplementedError

    def run(self):
        self.setup()
        self.prepare_db_server()
        if self.db_dump_path:
            # Only restore if we have something to restore
            self.restore_db()
        self.finish()

    def get_active_db_extensions(self):
        project_settings = utils.get_project_settings(self.path)
        default_db_extensions = ["hstore", "postgis"]

        if "db_extensions" in project_settings:
            if not isinstance(project_settings["db_extensions"], list):
                raise DivioException(
                    'Divio configuration file contains invalid "db_extensions" value. '
                    f"It should contain a list of extensions, for instance: {default_db_extensions}"
                )
            return project_settings["db_extensions"]
        else:
            return default_db_extensions

    def prepare_db_server_postgres(self, db_container_id, start_wait):
        for _attempt in range(10):
            try:
                check_call(
                    [
                        "docker",
                        "exec",
                        db_container_id,
                        "ls",
                        "/var/run/postgresql/.s.PGSQL.5432",
                    ],
                    catch=False,
                    silent=True,
                )
            except subprocess.CalledProcessError:
                sleep(5)
            else:
                break
        else:
            raise DivioException(
                "Couldn't connect to database container. "
                "Database server may not have started.",
            )
        click.echo(f" [{int(time() - start_wait)}s]")

        # drop any existing connections
        check_call(
            [
                "docker",
                "exec",
                db_container_id,
                "psql",
                "-U",
                "postgres",
                "-c",
                "SELECT pg_terminate_backend(pg_stat_activity.pid) "
                "FROM   pg_stat_activity "
                "WHERE  pg_stat_activity.datname = 'db' "
                "  AND  pid <> pg_backend_pid();",
            ],
            silent=True,
        )
        # sometimes postgres takes a while to drop the connections
        sleep(5)

        click.secho(" ---> Removing local database", nl=False)
        start_remove = time()
        # create empty db
        subprocess.call(
            [
                "docker",
                "exec",
                db_container_id,
                "dropdb",
                "-U",
                "postgres",
                "db",
                "--if-exists",
            ],
            env=get_subprocess_env(),
        )  # TODO: silence me

        click.echo(f" [{int(time() - start_remove)}s]")

    def prepare_db_server_mysql(self, db_container_id, start_wait):
        for _attempt in range(10):
            try:
                check_call(
                    [
                        "docker",
                        "exec",
                        db_container_id,
                        "/bin/bash",
                        "-c",
                        'mysql --user=root  --execute "SHOW DATABASES;"',
                    ],
                    catch=False,
                    silent=True,
                )
            except subprocess.CalledProcessError:
                sleep(5)
            else:
                break
        else:
            raise DivioException(
                "Couldn't connect to database container. "
                "Database server may not have started.",
            )
        click.echo(f" [{int(time() - start_wait)}s]")

    def prepare_db_server(self):
        utils.start_database_server(self.docker_compose, prefix=self.prefix)

        click.secho(" ---> Waiting for local database server", nl=False)

        db_container_id = utils.get_db_container_id(
            self.path, prefix=self.prefix
        )

        start_wait = time()
        # check for postgres in db container to start

        # sleep 10 seconds initially because the server is quickly
        # available during startup, but will go down again to
        # create the initial database. We're giving the database a head start
        sleep(10)

        if self.db_type == "fsm-postgres":
            self.prepare_db_server_postgres(db_container_id, start_wait)
        elif self.db_type == "fsm-mysql":
            self.prepare_db_server_mysql(db_container_id, start_wait)
        else:
            raise DivioException("db type not known")

    def get_db_restore_command(self, db_type):
        raise NotImplementedError

    def restore_db_postgres(self, db_container_id):
        restore_command = self.get_db_restore_command(self.db_type)
        # Create db
        check_call(
            [
                "docker",
                "exec",
                db_container_id,
                "createdb",
                "-U",
                "postgres",
                "db",
            ]
        )

        if self.database_extensions:
            available_extensions = check_output(
                [
                    "docker",
                    "exec",
                    db_container_id,
                    "psql",
                    "-U",
                    "postgres",
                    "--dbname=postgres",
                    "-c",
                    "SELECT name FROM pg_catalog.pg_available_extensions",
                ]
            )

            # TODO: solve extensions in a generic way in
            # harmony with server side db-api
            click.echo("")
            for extension in self.database_extensions:
                if extension in available_extensions:
                    click.echo(f"      Enabling extension: {extension}")
                    check_call(
                        [
                            "docker",
                            "exec",
                            db_container_id,
                            "psql",
                            "-U",
                            "postgres",
                            "--dbname=db",
                            "-c",
                            f"CREATE EXTENSION IF NOT EXISTS {extension};",
                        ],
                        silent=True,
                    )

        # TODO: use same dump-type detection like server side on db-api
        try:
            check_call(
                [
                    "docker",
                    "exec",
                    db_container_id,
                    "/bin/bash",
                    "-c",
                    restore_command,
                ],
                env=get_subprocess_env(),
                catch=False,
            )
        except subprocess.CalledProcessError as exc:
            raise DivioException(
                "Could not restore the database dump. This is likely a "
                "configuration issue."
                "\n\nSee https://docs.divio.com/en/latest/reference/docker-docker-compose/#services-defined-in-docker-compose-yml\n\n"
                "The executed command was:\n"
                "  {command}".format(command=" ".join(exc.cmd)),
            )

    def restore_db_mysql(self, db_container_id):
        restore_command = self.get_db_restore_command(self.db_type)

        check_call(
            [
                "docker",
                "exec",
                db_container_id,
                "/bin/bash",
                "-c",
                "mysql -u root --execute='CREATE DATABASE db;' > /dev/null 2>&1 | true",
            ]
        )

        check_call(
            (
                "docker",
                "exec",
                db_container_id,
                "/bin/bash",
                "-c",
                restore_command,
            ),
            env=get_subprocess_env(),
        )

    def restore_db(self):
        click.secho(" ---> Importing database", nl=False)
        start_import = time()

        db_container_id = utils.get_db_container_id(
            self.path, prefix=self.prefix
        )
        if self.db_type == "fsm-postgres":
            self.restore_db_postgres(db_container_id)
        elif self.db_type == "fsm-mysql":
            self.restore_db_mysql(db_container_id)
        else:
            raise DivioException("db type not known")
        click.echo(f"\n      [{int(time() - start_import)}s]")

    def finish(self):
        click.secho("Done", fg="green", nl=False)
        click.echo(f" [{int(time() - self.start_time)}s]")


class ImportLocalDatabase(DatabaseImportBase):
    def __init__(self, *args, **kwargs):
        self.custom_dump_path = kwargs.pop("custom_dump_path")
        super().__init__(*args, **kwargs)

    def setup(self):
        click.secho(
            f" ===> Loading database dump {self.custom_dump_path} into local {self.prefix} database"
        )
        db_container_id = utils.get_db_container_id(
            self.path, prefix=self.prefix
        )

        start_copy = time()

        click.secho(" ---> Copying dump into container", nl=False)
        check_call(
            [
                "docker",
                "cp",
                self.custom_dump_path,
                f"{db_container_id}:/tmp/dump",
            ],
            catch=False,
            silent=True,
        )
        click.echo(f" [{int(time() - start_copy)}s]")
        self.db_dump_path = "/tmp/dump"

    def get_db_restore_command(self, db_type):
        if self.custom_dump_path.endswith("sql"):
            kind = "sql"
        else:
            kind = "binary"
        return self.restore_commands[db_type][kind].format(self.db_dump_path)


class ImportRemoteDatabase(DatabaseImportBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.environment = kwargs.pop("environment", None)
        self.application_uuid = kwargs.pop("application_uuid", None)
        self.keep_tempfile = kwargs.pop("keep_tempfile", None)
        self.backup_si_uuid = kwargs.pop("backup_si_uuid", None)
        remote_project_name = f"Project {self.application_uuid}"

        click.secho(
            f" ===> Pulling database from {remote_project_name} {self.environment} environment"
        )

    def setup(self):
        if self.backup_si_uuid:
            with utils.TimedStep("Verifying backup instance"):
                backup_uuid = backups.get_backup_uuid_from_service_backup(
                    self.client, self.backup_si_uuid, backups.Type.DB
                )
        else:
            with utils.TimedStep("Creating backup"):
                backup_uuid, self.backup_si_uuid = backups.create_backup(
                    self.client,
                    self.application_uuid,
                    self.environment,
                    backups.Type.DB,
                    self.prefix,
                )

        with utils.TimedStep("Preparing download"):
            download_url = backups.create_backup_download_url(
                self.client, backup_uuid, self.backup_si_uuid
            )

        if download_url:
            # Create the dump target directory if it does not exist yet
            if not os.path.exists(self.dump_path):
                os.makedirs(self.dump_path)

            with utils.TimedStep("Downloading database"):
                self.host_db_dump_path = download_file(
                    download_url, directory=self.dump_path
                )
            utils.step(f"Writing temp file: {self.host_db_dump_path}")
            # strip path from dump_path for use in the docker container and ensure
            # posix path, even when running on Windows
            host_dump_path = re.findall(
                r"([^\/|^\\\\]+)",
                self.host_db_dump_path.replace(self.path, ""),
            )
            self.db_dump_path = PurePosixPath("/app", *host_dump_path)
        else:
            utils.step("empty database")
            self.db_dump_path = None
            self.host_db_dump_path = None

    def get_db_restore_command(self, db_type):
        cmd = self.restore_commands[db_type]["binary"]
        return cmd.format(self.db_dump_path)

    def finish(self, *args, **kwargs):
        if self.host_db_dump_path:
            if self.keep_tempfile:
                utils.step(f"Keeping temp file: {self.host_db_dump_path}")
            else:
                utils.step(f"Removing temp file: {self.host_db_dump_path}")
                os.remove(self.host_db_dump_path)
        super().finish(*args, **kwargs)


def pull_media(
    client,
    environment,
    prefix=None,
    application_uuid=None,
    path=None,
    backup_si_uuid=None,
    keep_tempfile=False,
):
    project_home = utils.get_application_home(path)
    application_uuid = utils.get_project_settings(project_home)[
        "application_uuid"
    ]
    remote_project_name = f"Project {application_uuid}"
    docker_compose = utils.get_docker_compose_cmd(project_home)
    docker_compose_config = utils.DockerComposeConfig(docker_compose)

    local_data_folder = os.path.join(project_home, "data")
    remote_data_folder = "/data"

    if not docker_compose_config.has_volume_mount("web", remote_data_folder):
        click.secho("No mount for /data folder found")
        return

    main_step = utils.MainStep(
        f"Pulling media files from {remote_project_name} {environment} environment"
    )
    if backup_si_uuid:
        with utils.TimedStep("Verifying backup instance"):
            backup_uuid = backups.get_backup_uuid_from_service_backup(
                client, backup_si_uuid, backups.Type.MEDIA
            )
    else:
        with utils.TimedStep(
            "Searching for an Object Storage service instance"
        ):
            from divio_cli.localdev.backups import Type

            environment_uuid = client.get_environment(
                application_uuid,
                environment,
            )["uuid"]

            service_instance = client.get_service_instance(
                Type.MEDIA,
                environment_uuid,
                prefix=prefix,
            )

            if (
                not service_instance
                or service_instance["service_status"] == "NEW"
            ):
                click.secho("No Object Storage service instance found")

                return

        with utils.TimedStep("Creating backup"):
            backup_uuid, backup_si_uuid = backups.create_backup(
                client,
                application_uuid,
                environment,
                backups.Type.MEDIA,
                prefix,
            )

    with utils.TimedStep("Preparing download"):
        download_url = backups.create_backup_download_url(
            client, backup_uuid, backup_si_uuid
        )

    with utils.TimedStep("Downloading"):
        directory = os.path.join(project_home, settings.DIVIO_DUMP_FOLDER)
        backup_path = download_file(download_url, directory=directory)
        if not backup_path:
            # no backup yet, skipping
            return
        click.secho(f"to {backup_path}", nl=False)

    media_path = os.path.join(local_data_folder, "media")

    if os.path.isdir(media_path):
        with utils.TimedStep("Removing local files"):
            shutil.rmtree(media_path)

    if "linux" in sys.platform:
        # On Linux, Docker typically runs as root, so files and folders
        # created from within the container will be owned by root. As a
        # workaround, make the folder permissions more permissive, to
        # allow the invoking user to create files inside it.
        try:
            check_call(
                docker_compose(
                    "run",
                    "--rm",
                    "web",
                    "chown",
                    str(os.getuid()),
                    remote_data_folder,
                ),
                catch=False,
            )
        except subprocess.CalledProcessError as exc:
            # This can happen due to a race condition in docker compose >= 2
            click.secho(
                f"Failed to set user ownership of media files.  {exc}\n",
                fg="yellow",
            )

    with utils.TimedStep(f"Extracting files to {media_path}"):
        with open(backup_path, "rb") as fobj:
            with tarfile.open(fileobj=fobj, mode="r:*") as media_archive:
                media_archive.extractall(path=media_path)

    if not keep_tempfile:
        with utils.TimedStep("Removing temporary files"):
            os.remove(backup_path)

    main_step.done()


def export_db(prefix):
    dump_filename = DEFAULT_DUMP_FILENAME

    click.secho(f" ===> Exporting local database {prefix} to {dump_filename}")
    start_time = time()

    project_home = utils.get_application_home()
    db_type = utils.get_db_type(prefix=prefix, path=project_home)
    dump_database(dump_filename=dump_filename, db_type=db_type, prefix=prefix)

    click.secho("Done", fg="green", nl=False)
    click.echo(f" [{int(time() - start_time)}s]")


def push_db(
    client,
    environment,
    application_uuid,
    prefix,
    local_file=None,
    keep_tempfile=True,
    binary=False,
):
    pusher = PushDb.create(
        client=client,
        environment=environment,
        application_uuid=application_uuid,
        prefix=prefix,
    )
    # do not cleanup after if the file was provided by the user or
    # he explicitly asked not to
    pusher.run(
        local_file=local_file,
        cleanup=not (local_file or keep_tempfile),
        binary=binary,
    )


def push_media(
    client, environment, application_uuid, prefix, keep_tempfile=True
):
    pusher = PushMedia.create(
        client=client,
        environment=environment,
        application_uuid=application_uuid,
        prefix=prefix,
    )
    pusher.run(cleanup=not keep_tempfile)


def update_local_application(git_branch, client, strict=False):
    """
    Makes all updates of the local project.
    """
    project_home = utils.get_application_home()
    try:
        docker_compose = utils.get_docker_compose_cmd(project_home)
    except DockerComposeDoesNotExist:
        # Docker-compose does not exist
        docker_compose = None

    # We also check for remote repository configurations on a project update
    # to warn the user just in case something changed
    remote_dsn = client.get_repository_dsn(
        utils.get_project_settings(utils.get_application_home())[
            "application_uuid"
        ]
    )

    if remote_dsn and remote_dsn not in get_local_git_remotes():
        click.secho(
            "Warning: The project has a git repository configured in the divio"
            " cloud which is not present in your local git configuration.",
            fg="yellow",
            err=True,
        )
        if strict:
            sys.exit(ExitCode.GENERIC_ERROR)

    click.secho("Pulling changes from git remote", fg="green")
    check_call(("git", "pull", "origin", git_branch))
    if docker_compose:
        click.secho("Pulling docker images", fg="green")
        check_call(docker_compose("pull"))
        click.secho("Building local docker images", fg="green")
        check_call(docker_compose("build"))
        if needs_legacy_migration():
            click.secho("syncing and migrating database", fg="green")
            if is_windows():
                # interactive mode is not yet supported with docker-compose
                # on windows. that's why we have to call it as daemon
                # and just wait a sane time
                check_call(
                    docker_compose("run", "-d", "web", "start", "migrate"),
                )
                sleep(30)
            else:
                check_call(
                    docker_compose("run", "web", "start", "migrate"),
                )


def develop_package(package, no_rebuild=False):
    """
    :param package: package name in addons-dev folder
    :param no_rebuild: skip the rebuild of the container
    """

    project_home = utils.get_application_home()
    addons_dev_dir = os.path.join(project_home, "addons-dev")

    if not os.path.isdir(os.path.join(addons_dev_dir, package)):
        raise DivioException(
            f"Package {package} could not be found in {addons_dev_dir}. "
            "Please make sure it exists and try again."
        )

    url_pattern = re.compile(rf"(\S*/{package}/\S*)")
    new_package_path = f"-e /app/addons-dev/{package}\n"

    # add package to requirements.in for dependencies
    requirements_file = os.path.join(project_home, "requirements.in")
    # open file with 'universal newline support'
    # https://docs.python.org/2/library/functions.html#open
    with open(requirements_file, "r") as fh:
        addons = fh.readlines()

    replaced = False

    for counter, addon in enumerate(addons):
        if re.match(url_pattern, addon) or addon == new_package_path:
            addons[counter] = new_package_path
            replaced = True
            break

    if not replaced:
        # Not replaced, append to generated part of requirements
        for counter, addon in enumerate(addons):
            if "</INSTALLED_ADDONS>" in addon:
                addons.insert(counter, new_package_path)
                replaced = True
                break

    if not replaced:
        # fallback: generated section seems to be missing, appending
        addons.append(new_package_path)

    with open(requirements_file, "w") as fh:
        fh.writelines(addons)

    if not no_rebuild:
        # build web again
        try:
            docker_compose = utils.get_docker_compose_cmd(project_home)
            check_call(docker_compose("build", "web"))
        except DockerComposeDoesNotExist as e:
            # Docker-compose does not exist
            raise DockerComposeDoesNotExist("Cannot rebuild project") from e

    click.secho(
        f"The package {package} has been added to your local development project!"
    )


def open_application(open_browser=True):
    docker_compose = utils.get_docker_compose_cmd(utils.get_application_home())
    CHECKING_PORT = "80"
    try:
        addr = check_output(
            docker_compose("port", "web", CHECKING_PORT), catch=False
        )
    except subprocess.CalledProcessError:
        if click.prompt(
            "Your project is not running. Do you want to start it now? [y|N]"
        ):
            return start_application()
        return None
    try:
        host, port = addr.rstrip(os.linesep).split(":")
    except ValueError:
        raise DivioException(
            "Can not get port of the project. Please check `docker-compose logs` in case the project "
            f"did not start correctly and please verify that a port {CHECKING_PORT} is exposed."
        )

    if host == "0.0.0.0":
        docker_host_url = os.environ.get("DOCKER_HOST")
        if docker_host_url:
            proto, host_port = os.environ.get("DOCKER_HOST").split("://")
            host = host_port.split(":")[0]

    addr = f"http://{host}:{port}/"

    click.secho(f"Your project is configured to run at {addr}", fg="green")

    click.secho("Waiting for project to start..", fg="green", nl=False)
    # wait 30s for runserver to startup
    seconds = 30
    for _attempt in range(seconds):
        click.secho(".", fg="green", nl=False)
        try:
            requests.head(addr)
        except requests.ConnectionError:
            sleep(1)
        else:
            click.echo()
            break
    else:
        raise DivioException(
            "\nProject failed to start. Please run 'docker-compose logs' "
            "to get more information."
        )

    if open_browser:
        launch_url(addr)
    return addr


def configure(client, zone=None):
    if click.confirm(
        "This action will overwrite the local Divio configuration file for your project or create a new one. Do you want to continue?"
    ):
        website_slug = click.prompt(
            "Please enter the application slug of the local project", type=str
        )
        configure_project(
            website_slug=website_slug,
            path=os.getcwd(),
            client=client,
            zone=zone,
        )


def start_application():
    docker_compose = utils.get_docker_compose_cmd(utils.get_application_home())
    try:
        check_output(
            docker_compose("up", "-d"), catch=False, stderr=subprocess.STDOUT
        )
    except subprocess.CalledProcessError as exc:
        output = exc.output.decode()
        if "port is already allocated" in output:
            output = (
                "There's already another program running on this project's "
                "port. Please either stop the other program or change the "
                "port in the 'docker-compose.yml' file and try again.\n"
            )
        raise DivioException(output)

    return open_application(open_browser=True)


def show_application_status():
    docker_compose = utils.get_docker_compose_cmd(utils.get_application_home())
    check_call(docker_compose("ps"))


def stop_application():
    docker_compose = utils.get_docker_compose_cmd(utils.get_application_home())
    check_call(docker_compose("stop"))
