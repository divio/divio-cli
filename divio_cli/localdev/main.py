import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
from time import sleep, time

import click
import requests

from . import utils
from .. import settings
from ..cloud import get_aldryn_host
from ..utils import (
    check_call,
    check_output,
    download_file,
    get_size,
    get_subprocess_env,
    is_windows,
    pretty_size,
)

DEFAULT_GIT_HOST = "git@git.{aldryn_host}"
GIT_CLONE_URL = "{git_host}:{project_slug}.git"


def get_git_host():
    git_host = os.environ.get("ALDRYN_GIT_HOST")
    if git_host:
        click.secho("Using custom git host {}\n".format(git_host), fg="yellow")
    else:
        git_host = DEFAULT_GIT_HOST.format(aldryn_host=get_aldryn_host())
    return git_host


def get_git_clone_url(slug):
    return GIT_CLONE_URL.format(git_host=get_git_host(), project_slug=slug)


def clone_project(website_slug, path):
    click.secho("\ncloning project repository", fg="green")
    website_git_url = get_git_clone_url(website_slug)
    clone_args = ["git", "clone", website_git_url]
    if path:
        clone_args.append(path)

    check_call(clone_args)


def configure_project(website_slug, path, client):
    website_id = client.get_website_id_for_slug(website_slug)

    # Detect old style or invalid projects
    compose_config = os.path.join(path, "docker-compose.yml")
    if not os.path.isfile(compose_config):
        raise click.ClickException(
            "Could not find a valid 'docker-compose.yml' file. Please make "
            "sure that this project has been updated on the Divio Cloud to "
            "use Base Project version 3 or higher."
        )

    # create .aldryn file
    website_data = {"id": website_id, "slug": website_slug}
    with open(os.path.join(path, settings.ALDRYN_DOT_FILE), "w+") as fh:
        json.dump(website_data, fh)


def setup_website_containers(client, stage, path):
    docker_compose = utils.get_docker_compose_cmd(path)
    docker_compose_config = utils.DockerComposeConfig(docker_compose)

    if docker_compose_config.has_service("db"):
        has_db_service = True
        existing_db_container_id = utils.get_db_container_id(
            path=path, raise_on_missing=False
        )
    else:
        has_db_service = False
        existing_db_container_id = None

    # stop all running containers for project
    check_call(docker_compose("stop"))

    # pull docker images
    click.secho("downloading remote docker images", fg="green")
    check_call(docker_compose("pull"))

    # build docker images
    click.secho("building local docker images", fg="green")
    check_call(docker_compose("build"))

    if existing_db_container_id:
        click.secho("removing old database container", fg="green")
        check_call(docker_compose("stop", "db"))
        check_call(docker_compose("rm", "-f", "db"))

    if has_db_service:
        click.secho("creating new database container", fg="green")
        ImportRemoteDatabase(client=client, stage=stage, path=path)()

        click.secho("syncing and migrating database", fg="green")

        if is_windows():
            # interactive mode is not yet supported with docker-compose
            # on windows. that's why we have to call it as daemon
            # and just wait a sane time
            check_call(docker_compose("run", "-d", "web", "start", "migrate"))
            sleep(30)
        else:
            check_call(docker_compose("run", "web", "start", "migrate"))


def create_workspace(
    client, website_slug, stage, path=None, force_overwrite=False
):
    click.secho("Creating workspace", fg="green")

    path = os.path.abspath(
        os.path.join(path, website_slug) if path else website_slug
    )

    if os.path.exists(path) and (not os.path.isdir(path) or os.listdir(path)):
        if force_overwrite or click.confirm(
            "The path {} already exists and is not an empty directory. "
            "Do you want to remove it and continue?".format(path)
        ):
            if os.path.isdir(path):

                def del_rw(action, name, exc):
                    os.chmod(name, stat.S_IWRITE)
                    os.remove(name)

                shutil.rmtree(path, onerror=del_rw)
            else:
                os.remove(path)
        else:
            click.secho("Aborting", fg="red")
            sys.exit(1)

    # clone git project
    clone_project(website_slug=website_slug, path=path)

    # check for new baseproject + add .aldryn
    configure_project(website_slug=website_slug, path=path, client=client)

    # setup docker website containers
    setup_website_containers(client=client, stage=stage, path=path)

    # download media files
    pull_media(client=client, stage=stage, path=path)

    instructions = (
        "Your workspace is setup and ready to start.",
        "",
        "For Desktop Application:",
        " - click on the 'Start' button",
        "",
        "For Terminal:",
        " - change directory to '{}'".format(path),
        " - run 'divio project up'",
    )

    click.secho("\n\n{}".format(os.linesep.join(instructions)), fg="green")


class DatabaseImportBase(object):
    restore_commands = {
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
    }

    def __init__(self, *args, **kwargs):
        super(DatabaseImportBase, self).__init__()
        self.client = kwargs.pop("client")
        self.path = kwargs.pop("path", None) or utils.get_project_home()
        self.website_id = utils.get_aldryn_project_settings(self.path)["id"]
        self.website_slug = utils.get_aldryn_project_settings(self.path)[
            "slug"
        ]
        self.docker_compose = utils.get_docker_compose_cmd(self.path)
        self.database_extensions = self.get_active_db_extensions()
        docker_compose_config = utils.DockerComposeConfig(self.docker_compose)
        if not docker_compose_config.has_service("db"):
            click.secho('No service "db" found in local project', fg="red")
            sys.exit(1)

        self.start_time = time()

    def __call__(self, *args, **kwargs):
        return self.run()

    def setup(self):
        raise NotImplementedError

    def run(self):
        self.setup()
        self.prepare_db_server()
        self.restore_db()
        self.finish()

    def get_active_db_extensions(self):
        project_settings = utils.get_aldryn_project_settings(self.path)
        default_db_extensions = ["hstore", "postgis"]

        if "db_extensions" in project_settings:
            if not isinstance(project_settings["db_extensions"], list):
                raise click.ClickException(
                    '{} file contains invalid "db_extensions" value. '
                    "It should contain a list of extensions, for instance: {}".format(
                        settings.ALDRYN_DOT_FILE, default_db_extensions
                    )
                )
            return project_settings["db_extensions"]
        else:
            return default_db_extensions

    def prepare_db_server(self):
        utils.start_database_server(self.docker_compose)

        click.secho(" ---> Waiting for local database server", nl=False)

        db_container_id = utils.get_db_container_id(self.path)

        start_wait = time()
        # check for postgres in db container to start

        # sleep 5 seconds initially because the server is quickly
        # available during startup, but will go down again to
        # create the initial database. We're giving postgres a head start
        sleep(5)

        for attempt in range(10):
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
            click.secho(
                "Couldn't connect to database container. "
                "Database server may not have started.",
                fg="red",
            )
            sys.exit(1)
        click.echo(" [{}s]".format(int(time() - start_wait)))

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

        click.echo(" [{}s]".format(int(time() - start_remove)))

    def get_db_restore_command(self):
        raise NotImplementedError

    def restore_db(self):
        click.secho(" ---> Importing database", nl=False)
        start_import = time()

        db_container_id = utils.get_db_container_id(self.path)

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
                    click.echo(
                        "      Enabling extension: {}".format(extension)
                    )
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
                            "CREATE EXTENSION IF NOT EXISTS {};".format(
                                extension
                            ),
                        ],
                        silent=True,
                    )

        restore_command = self.get_db_restore_command()

        # TODO: use same dump-type detection like server side on db-api
        try:
            subprocess.call(
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
        except subprocess.CalledProcessError:
            pass

        click.echo("\n      [{}s]".format(int(time() - start_import)))

    def finish(self):
        click.secho("Done", fg="green", nl=False)
        click.echo(" [{}s]".format(int(time() - self.start_time)))


class ImportLocalDatabase(DatabaseImportBase):
    def __init__(self, *args, **kwargs):
        self.custom_dump_path = kwargs.pop("custom_dump_path")
        super(ImportLocalDatabase, self).__init__(*args, **kwargs)

    def setup(self):
        click.secho(
            " ===> Loading database dump {} into local database".format(
                self.custom_dump_path
            )
        )
        db_container_id = utils.get_db_container_id(self.path)

        start_copy = time()

        click.secho(" ---> Copying dump into container", nl=False)
        check_call(
            [
                "docker",
                "cp",
                self.custom_dump_path,
                "{}:/tmp/dump".format(db_container_id),
            ],
            catch=False,
            silent=True,
        )
        click.echo(" [{}s]".format(int(time() - start_copy)))
        self.db_dump_path = "/tmp/dump"

    def get_db_restore_command(self):
        if self.custom_dump_path.endswith("sql"):
            kind = "sql"
        else:
            kind = "binary"
        return self.restore_commands[kind].format(self.db_dump_path)


class ImportRemoteDatabase(DatabaseImportBase):
    def __init__(self, *args, **kwargs):
        super(ImportRemoteDatabase, self).__init__(*args, **kwargs)
        self.stage = kwargs.pop("stage", None)
        self.remote_id = kwargs.pop("remote_id", None) or self.website_id
        remote_project_name = (
            self.website_slug
            if self.remote_id == self.website_id
            else "Project {}".format(self.remote_id)
        )
        click.secho(
            " ===> Pulling database from {} {} server".format(
                remote_project_name, self.stage
            )
        )

    def setup(self):
        click.secho(" ---> Preparing download", nl=False)
        start_preparation = time()
        response = (
            self.client.download_db_request(self.remote_id, self.stage) or {}
        )
        progress_url = response.get("progress_url")
        if not progress_url:
            click.secho(" error!", fg="red")
            sys.exit(1)
        progress = {"success": None}
        while progress.get("success") is None:
            sleep(2)
            progress = self.client.download_db_progress(url=progress_url)
        if not progress.get("success"):
            click.secho(" error!", fg="red")
            click.secho(progress.get("result") or "")
            sys.exit(1)
        download_url = progress.get("result") or None
        click.echo(" [{}s]".format(int(time() - start_preparation)))

        click.secho(" ---> Downloading database", nl=False)
        start_download = time()
        db_dump_path = download_file(download_url, directory=self.path)
        click.echo(" [{}s]".format(int(time() - start_download)))
        # strip path from dump_path for use in the docker container
        self.db_dump_path = "/app/{}".format(
            db_dump_path.replace(self.path, "")
        )

    def get_db_restore_command(self):
        cmd = self.restore_commands["archived-binary"]
        return cmd.format(self.db_dump_path)


def pull_media(client, stage, remote_id=None, path=None):
    project_home = utils.get_project_home(path)
    website_id = utils.get_aldryn_project_settings(project_home)["id"]
    website_slug = utils.get_aldryn_project_settings(project_home)["slug"]
    remote_id = remote_id or website_id
    remote_project_name = (
        website_slug
        if remote_id == website_id
        else "Project {}".format(remote_id)
    )
    docker_compose = utils.get_docker_compose_cmd(project_home)
    docker_compose_config = utils.DockerComposeConfig(docker_compose)

    local_data_folder = os.path.join(project_home, "data")
    remote_data_folder = "/data"

    if not docker_compose_config.has_volume_mount("web", remote_data_folder):
        click.secho("No mount for /data folder found")
        return

    click.secho(
        " ===> Pulling media files from {} {} server".format(
            remote_project_name, stage
        )
    )
    start_time = time()
    click.secho(" ---> Preparing download", nl=False)
    start_preparation = time()
    response = client.download_media_request(remote_id, stage) or {}
    progress_url = response.get("progress_url")
    if not progress_url:
        click.secho(" error!", fg="red")
        sys.exit(1)

    progress = {"success": None}
    while progress.get("success") is None:
        sleep(2)
        progress = client.download_media_progress(url=progress_url)
    if not progress.get("success"):
        click.secho(" error!", fg="red")
        click.secho(progress.get("result") or "")
        sys.exit(1)
    download_url = progress.get("result") or None
    click.echo(" [{}s]".format(int(time() - start_preparation)))

    click.secho(" ---> Downloading", nl=False)
    start_download = time()
    backup_path = download_file(download_url)
    if not backup_path:
        # no backup yet, skipping
        return
    click.echo(" [{}s]".format(int(time() - start_download)))

    media_path = os.path.join(local_data_folder, "media")

    if os.path.isdir(media_path):
        start_remove = time()
        click.secho(" ---> Removing local files", nl=False)
        shutil.rmtree(media_path)
        click.echo(" [{}s]".format(int(time() - start_remove)))

    if "linux" in sys.platform:
        # On Linux, Docker typically runs as root, so files and folders
        # created from within the container will be owned by root. As a
        # workaround, make the folder permissions more permissive, to
        # allow the invoking user to create files inside it.
        check_call(
            docker_compose(
                "run",
                "--rm",
                "web",
                "chown",
                "-R",
                str(os.getuid()),
                remote_data_folder,
            )
        )

    click.secho(" ---> Extracting files to {}".format(media_path), nl=False)
    start_extract = time()
    with open(backup_path, "rb") as fobj:
        with tarfile.open(fileobj=fobj, mode="r:*") as media_archive:
            media_archive.extractall(path=media_path)
    os.remove(backup_path)
    click.echo(" [{}s]".format(int(time() - start_extract)))
    click.secho("Done", fg="green", nl=False)
    click.echo(" [{}s]".format(int(time() - start_time)))


def dump_database(dump_filename, archive_filename=None):
    project_home = utils.get_project_home()
    docker_compose = utils.get_docker_compose_cmd(project_home)
    docker_compose_config = utils.DockerComposeConfig(docker_compose)
    if not docker_compose_config.has_service("db"):
        click.secho('No service "db" found in local project', fg="red")
        sys.exit(1)

    utils.start_database_server(docker_compose)

    click.secho(" ---> Dumping local database", nl=False)
    start_dump = time()
    db_container_id = utils.get_db_container_id(project_home)
    subprocess.call(
        (
            "docker",
            "exec",
            db_container_id,
            "pg_dump",
            "-U",
            "postgres",
            "-d",
            "db",
            "--no-owner",
            "--no-privileges",
            "-f",
            os.path.join("/app/", dump_filename),
        ),
        env=get_subprocess_env(),
    )
    click.echo(" [{}s]".format(int(time() - start_dump)))

    if not archive_filename:
        # archive filename not specified
        # return path to uncompressed dump
        return os.path.join(project_home, dump_filename)

    archive_path = os.path.join(project_home, archive_filename)
    sql_dump_size = os.path.getsize(dump_filename)
    click.secho(
        " ---> Compressing SQL dump ({})".format(pretty_size(sql_dump_size)),
        nl=False,
    )
    start_compress = time()
    with tarfile.open(archive_path, mode="w:gz") as tar:
        tar.add(
            os.path.join(project_home, dump_filename), arcname=dump_filename
        )
    compressed_size = os.path.getsize(archive_filename)
    click.echo(
        " {} [{}s]".format(
            pretty_size(compressed_size), int(time() - start_compress)
        )
    )


def compress_db(dump_filename, archive_filename=None, archive_wd=None):

    if not archive_filename:
        # archive filename not specified
        # return path to uncompressed dump
        return os.path.join(archive_wd, dump_filename)

    archive_path = os.path.join(archive_wd, archive_filename)
    sql_dump_size = os.path.getsize(dump_filename)
    click.secho(
        " ---> Compressing SQL dump ({})".format(pretty_size(sql_dump_size)),
        nl=False,
    )
    start_compress = time()
    with tarfile.open(archive_path, mode="w:gz") as tar:
        tar.add(os.path.join(archive_wd, dump_filename), arcname=dump_filename)
    compressed_size = os.path.getsize(archive_filename)
    click.echo(
        " {} [{}s]".format(
            pretty_size(compressed_size), int(time() - start_compress)
        )
    )


DEFAULT_DUMP_FILENAME = "local_db.sql"


def export_db():
    dump_filename = DEFAULT_DUMP_FILENAME

    click.secho(" ===> Exporting local database to {}".format(dump_filename))
    start_time = time()

    dump_database(dump_filename=dump_filename)

    click.secho("Done", fg="green", nl=False)
    click.echo(" [{}s]".format(int(time() - start_time)))


def push_db(client, stage, remote_id):
    project_home = utils.get_project_home()
    website_id = utils.get_aldryn_project_settings(project_home)["id"]
    dump_filename = DEFAULT_DUMP_FILENAME
    archive_filename = dump_filename.replace(".sql", ".tar.gz")
    archive_path = os.path.join(project_home, archive_filename)
    website_slug = utils.get_aldryn_project_settings(project_home)["slug"]
    remote_project_name = (
        website_slug
        if remote_id == website_id
        else "Project {}".format(remote_id)
    )

    click.secho(
        " ===> Pushing local database to {} {} server".format(
            remote_project_name, stage
        )
    )
    start_time = time()

    dump_database(
        dump_filename=dump_filename, archive_filename=archive_filename
    )

    click.secho(" ---> Uploading", nl=False)
    start_upload = time()
    response = client.upload_db(remote_id, stage, archive_path) or {}
    click.echo(" [{}s]".format(int(time() - start_upload)))

    progress_url = response.get("progress_url")
    if not progress_url:
        click.secho(" error!", fg="red")
        sys.exit(1)

    click.secho(" ---> Processing", nl=False)
    start_processing = time()
    progress = {"success": None}
    while progress.get("success") is None:
        sleep(2)
        progress = client.upload_db_progress(url=progress_url)
    if not progress.get("success"):
        click.secho(" error!", fg="red")
        click.secho(progress.get("result") or "")
        sys.exit(1)
    click.echo(" [{}s]".format(int(time() - start_processing)))

    # clean up
    for temp_file in (dump_filename, archive_filename):
        os.remove(os.path.join(project_home, temp_file))
    click.secho("Done", fg="green", nl=False)
    click.echo(" [{}s]".format(int(time() - start_time)))


def push_local_db(client, stage, dump_filename, website_id):
    archive_wd = os.path.dirname(os.path.realpath(dump_filename))
    archive_filename = dump_filename.replace(".sql", ".tar.gz")
    archive_path = os.path.join(archive_wd, archive_filename)

    click.secho(
        " ===> Pushing local database to {} {} server".format(
            website_id, stage
        )
    )
    start_time = time()

    compress_db(
        dump_filename=dump_filename,
        archive_filename=archive_filename,
        archive_wd=archive_wd,
    )

    click.secho(" ---> Uploading", nl=False)
    start_upload = time()
    response = client.upload_db(website_id, stage, archive_path) or {}
    click.echo(" [{}s]".format(int(time() - start_upload)))

    progress_url = response.get("progress_url")
    if not progress_url:
        click.secho(" error!", fg="red")
        sys.exit(1)

    click.secho(" ---> Processing", nl=False)
    start_processing = time()
    progress = {"success": None}
    while progress.get("success") is None:
        sleep(2)
        progress = client.upload_db_progress(url=progress_url)
    if not progress.get("success"):
        click.secho(" error!", fg="red")
        click.secho(progress.get("result") or "")
        sys.exit(1)
    click.echo(" [{}s]".format(int(time() - start_processing)))

    # clean up
    for temp_file in (dump_filename, archive_filename):
        os.remove(os.path.join(archive_wd, temp_file))
    click.secho("Done", fg="green", nl=False)
    click.echo(" [{}s]".format(int(time() - start_time)))


def push_media(client, stage, remote_id):
    project_home = utils.get_project_home()
    website_id = utils.get_aldryn_project_settings(project_home)["id"]
    archive_path = os.path.join(project_home, "local_media.tar.gz")
    website_slug = utils.get_aldryn_project_settings(project_home)["slug"]
    remote_project_name = (
        website_slug
        if remote_id == website_id
        else "Project {}".format(remote_id)
    )

    click.secho(
        " ---> Pushing local media to {} {} server".format(
            remote_project_name, stage
        )
    )
    start_time = time()
    click.secho("Compressing local media folder", nl=False)
    uncompressed_size = 0
    start_compression = time()
    with tarfile.open(archive_path, mode="w:gz") as tar:
        media_dir = os.path.join(project_home, "data", "media")
        if os.path.isdir(media_dir):
            items = os.listdir(media_dir)
        else:
            items = []

        if not items:
            click.secho("\nError: Local media directory is empty", fg="red")
            sys.exit(1)

        for item in items:
            if item == "MANIFEST":
                # partial uploads are currently not supported
                # not including MANIFEST to do a full restore
                continue
            file_path = os.path.join(media_dir, item)
            tar.add(file_path, arcname=item)
            uncompressed_size += get_size(file_path)
        file_count = len(tar.getmembers())
    click.echo(
        " {} {} ({}) compressed to {} [{}s]".format(
            file_count,
            "files" if file_count > 1 else "file",
            pretty_size(uncompressed_size),
            pretty_size(os.path.getsize(archive_path)),
            int(time() - start_compression),
        )
    )
    click.secho("Uploading", nl=False)
    start_upload = time()
    response = client.upload_media(remote_id, stage, archive_path) or {}
    click.echo(" [{}s]".format(int(time() - start_upload)))
    progress_url = response.get("progress_url")
    if not progress_url:
        click.secho(" error!", fg="red")
        sys.exit(1)

    click.secho("Processing", nl=False)
    start_processing = time()
    progress = {"success": None}
    while progress.get("success") is None:
        sleep(2)
        progress = client.upload_media_progress(url=progress_url)
    if not progress.get("success"):
        click.secho(" error!", fg="red")
        click.secho(progress.get("result") or "")
        sys.exit(1)
    click.echo(" [{}s]".format(int(time() - start_processing)))

    # clean up
    os.remove(archive_path)
    click.secho("Done", fg="green", nl=False)
    click.echo(" [{}s]".format(int(time() - start_time)))


def update_local_project(git_branch):
    project_home = utils.get_project_home()
    docker_compose = utils.get_docker_compose_cmd(project_home)

    click.secho("Pulling changes from git remote", fg="green")
    check_call(("git", "pull", "origin", git_branch))
    click.secho("Pulling docker images", fg="green")
    check_call(docker_compose("pull"))
    click.secho("Building local docker images", fg="green")
    check_call(docker_compose("build"))
    click.secho("syncing and migrating database", fg="green")
    if is_windows():
        # interactive mode is not yet supported with docker-compose
        # on windows. that's why we have to call it as daemon
        # and just wait a sane time
        check_call(docker_compose("run", "-d", "web", "start", "migrate"))
        sleep(30)
    else:
        check_call(docker_compose("run", "web", "start", "migrate"))


def develop_package(package, no_rebuild=False):
    """
    :param package: package name in addons-dev folder
    :param no_rebuild: skip the rebuild of the container
    """

    project_home = utils.get_project_home()
    addons_dev_dir = os.path.join(project_home, "addons-dev")

    if not os.path.isdir(os.path.join(addons_dev_dir, package)):
        raise click.ClickException(
            "Package {} could not be found in {}. Please make "
            "sure it exists and try again.".format(package, addons_dev_dir)
        )

    url_pattern = re.compile("(\S*/{}/\S*)".format(package))
    new_package_path = "-e /app/addons-dev/{}\n".format(package)

    # add package to requirements.in for dependencies
    requirements_file = os.path.join(project_home, "requirements.in")
    # open file with 'universal newline support'
    # https://docs.python.org/2/library/functions.html#open
    with open(requirements_file, "rU") as fh:
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
        docker_compose = utils.get_docker_compose_cmd(project_home)

        check_call(docker_compose("build", "web"))

    click.secho(
        "The package {} has been added to your local development project!".format(
            package
        )
    )


def open_project(open_browser=True):
    docker_compose = utils.get_docker_compose_cmd(utils.get_project_home())
    try:
        addr = check_output(docker_compose("port", "web", "80"), catch=False)
    except subprocess.CalledProcessError:
        if click.prompt(
            "Your project is not running. Do you want to start " "it now?"
        ):
            return start_project()
        return
    host, port = addr.rstrip(os.linesep).split(":")

    if host == "0.0.0.0":
        docker_host_url = os.environ.get("DOCKER_HOST")
        if docker_host_url:
            proto, host_port = os.environ.get("DOCKER_HOST").split("://")
            host = host_port.split(":")[0]

    addr = "http://{}:{}/".format(host, port)

    click.secho(
        "Your project is configured to run at {}".format(addr), fg="green"
    )

    click.secho("Waiting for project to start..", fg="green", nl=False)
    # wait 30s for runserver to startup
    seconds = 30
    for attempt in range(seconds):
        click.secho(".", fg="green", nl=False)
        try:
            requests.head(addr)
        except requests.ConnectionError:
            sleep(1)
        else:
            click.echo()
            break
    else:
        raise click.ClickException(
            "\nProject failed to start. Please run 'docker-compose logs' "
            "to get more information."
        )

    if open_browser:
        click.launch(addr)
    return addr


def start_project():
    docker_compose = utils.get_docker_compose_cmd(utils.get_project_home())
    try:
        check_output(
            docker_compose("up", "-d"), catch=False, stderr=subprocess.STDOUT
        )
    except subprocess.CalledProcessError as exc:
        output = exc.output.decode()
        if "port is already allocated" in output:
            click.secho(
                "There's already another program running on this project's "
                "port. Please either stop the other program or change the "
                "port in the 'docker-compose.yml' file and try again.\n",
                fg="red",
            )
        raise click.ClickException(output)

    return open_project(open_browser=True)


def show_project_status():
    docker_compose = utils.get_docker_compose_cmd(utils.get_project_home())
    check_call(docker_compose("ps"))


def stop_project():
    docker_compose = utils.get_docker_compose_cmd(utils.get_project_home())
    check_call(docker_compose("stop"))
