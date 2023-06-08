import os
import subprocess
import tarfile
import time

import click

from divio_cli.cloud import CloudClient
from divio_cli.localdev import backups, utils
from divio_cli.utils import get_size, get_subprocess_env, pretty_size


class PushBase:
    """A base class for db and media push"""

    def __init__(
        self,
        client: CloudClient,
        environment: str,
        remote_id: str,
        prefix: str,
        type: backups.Type,
    ):
        self.client = client
        self.environment = environment
        self.prefix = (prefix or "default").upper()
        self.type = type

        self.project_home = utils.get_application_home()
        settings = utils.get_project_settings(self.project_home)
        self.website_id = settings["id"]

        # Find the matching service instance for the given service type
        env = client.get_environment(self.website_id, environment)
        self.env_uuid = env["uuid"]
        si = client.get_service_instance(type, self.env_uuid, prefix)
        self.si_uuid = si["uuid"]

        self.remote_project_name = (
            settings["slug"]
            if self.website_id == remote_id
            else f"project {remote_id}"
        )

    def run(self, local_file=None, cleanup=True):
        main_step = utils.MainStep(
            "pushing local %s to %s's %s environment"
            % (
                self.type.lower(),
                self.remote_project_name,
                self.environment,
            )
        )

        if local_file:
            self.verify_step(local_file)
            self.local_file = local_file
        else:
            self.local_file = self.export_step()

        self.upload_step()
        self.restore_step()

        if cleanup:
            # TODO: this won't be called on errors and we can't use a
            # try/finally as we use exit() instead of throwing exceptions.
            self.cleanup_step()

        main_step.done()

    def verify_step(self, local_file):
        """Verify a given file has the expected format"""
        if not os.path.exists(local_file):
            utils.exit(f"File {local_file} does not exist.")

    def export_step(self) -> str:
        """Export dump/media and return the local file path"""
        raise NotImplementedError

    def upload_step(self):
        assert self.local_file
        assert self.si_uuid

        with utils.TimedStep("Uploading"):
            self.backup_uuid, self.si_backup_uuid = backups.upload_backup(
                client=self.client,
                environment_uuid=self.env_uuid,
                si_uuid=self.si_uuid,
                local_file=self.local_file,
            )

    def restore_step(self):
        assert self.si_uuid and self.backup_uuid and self.si_backup_uuid

        with utils.TimedStep("Restoring"):
            res = self.client.create_backup_restore(
                backup_uuid=self.backup_uuid,
                si_backup_uuid=self.si_backup_uuid,
            )
            restore_uuid = res["uuid"]

            restore = {}
            while not restore.get("finished", False):
                time.sleep(2)
                restore = self.client.get_backup_restore(restore_uuid)
            if restore.get("success") != "SUCCESS":
                utils.exit("Backup restore failed.")

    def cleanup_step(self):
        with utils.TimedStep("Deleting temporary files"):
            if self.local_file and os.path.exists(self.local_file):
                os.remove(self.local_file)


class PushMedia(PushBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, type=backups.Type.MEDIA, **kwargs)

    def verify_step(self, local_file):
        super().verify_step(local_file)
        if not tarfile.is_tarfile(local_file):
            utils.exit(f"Given file {local_file} is not a tarball.")

    def export_step(self):
        compress_step = utils.TimedStep("Compressing local media folder")
        archive_path = os.path.join(self.project_home, "local_media.tar.gz")
        media_dir = os.path.join(self.project_home, "data", "media")

        items = os.listdir(media_dir) if os.path.isdir(media_dir) else []
        if not items:
            utils.exit("Local media directory is empty")

        uncompressed_size = 0
        with tarfile.open(archive_path, mode="w:gz") as tar:
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
            " {} {} ({}) compressed to {}".format(
                file_count,
                "files" if file_count > 1 else "file",
                pretty_size(uncompressed_size),
                pretty_size(os.path.getsize(archive_path)),
            ),
            nl=False,
        )

        compress_step.done()
        return archive_path


class PushDb(PushBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, type=backups.Type.DB, **kwargs)

    def verify_step(self, local_file):
        super().verify_step(local_file)
        db_type = utils.get_db_type(self.prefix, path=self.project_home)
        if not is_db_dump(local_file, db_type):
            utils.exit(f"File {local_file} doesn't look like a database dump")

    def export_step(self):
        # Avoid circular imports
        from divio_cli.localdev.main import DEFAULT_DUMP_FILENAME

        local_file = DEFAULT_DUMP_FILENAME
        db_type = utils.get_db_type(self.prefix, path=self.project_home)

        dump_database(
            dump_filename=local_file,
            db_type=db_type,
            prefix=self.prefix,
        )  # FIXME: what if empty or no docker?

        return os.path.join(self.project_home, local_file)


def is_db_dump(local_file: str, db_type: str):
    """Test if a file looks like a database dump"""
    start_bytes = open(local_file, "rb").read(1024)
    if db_type == "fsm-postgres":
        if start_bytes.startswith(b"\x50\x47\x44\x42"):
            return True  # postgres binary dump
    if start_bytes.startswith(b"--") and b"dump" in start_bytes.lower():
        return True  # plaintext dump
    return False


def dump_database(
    dump_filename: str, db_type: str, prefix: str, archive_filename: str = None
):
    """
    Dump a database running in docker.
    Return the path to a regular or a compressed dump (.tar.gz) depending on
    whether `archive_filename` is set.
    """
    project_home = utils.get_application_home()
    try:
        docker_compose = utils.get_docker_compose_cmd(project_home)
    except RuntimeError:
        # Docker-compose does not exist
        utils.exit(
            "Docker-compose.yml does not exist. Can not handle database without!",
        )
        return
    utils.DockerComposeConfig(docker_compose)
    utils.start_database_server(docker_compose, prefix=prefix)

    dump_step = utils.TimedStep("Dumping local database")
    db_container_id = utils.get_db_container_id(project_home, prefix=prefix)
    # TODO: database
    if db_type == "fsm-postgres":
        return_code = subprocess.call(
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

    elif db_type == "fsm-mysql":
        with open(dump_filename, "w") as f:
            return_code = subprocess.call(
                (
                    "docker",
                    "exec",
                    db_container_id,
                    "mysqldump",
                    "--user=root",
                    "--compress",
                    "db",
                ),
                env=get_subprocess_env(),
                stdout=f,
            )

    else:
        utils.exit("db type not known")

    if return_code != 0:
        utils.exit("Error dumping the database")

    dump_step.done()

    if not archive_filename:
        # archive filename not specified -> return uncompressed dump
        return os.path.join(project_home, dump_filename)

    archive_path = os.path.join(project_home, archive_filename)
    sql_dump_size = os.path.getsize(dump_filename)
    with utils.TimedStep(
        f"Compressing SQL dump {pretty_size(sql_dump_size)} "
    ):
        with tarfile.open(archive_path, mode="w:gz") as tar:
            tar.add(
                os.path.join(project_home, dump_filename),
                arcname=dump_filename,
            )
        compressed_size = os.path.getsize(archive_filename)
        click.echo(f"-> {pretty_size(compressed_size)}")
