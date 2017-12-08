import hashlib
import os
import sys
from time import time

import boto3
from boto3.s3.transfer import create_transfer_manager, TransferConfig
from botocore.client import Config
import click

from . import utils
from ..utils import check_call


class BaseS3SyncCommand(object):
    PREFIX = 'media'
    DATA_FOLDER = 'data'

    # S3 settings
    S3_MULTIPART_THRESHOLD = 1024 * 1024 * 64
    S3_MULTIPART_CHUNKSIZE = 1024 * 1024 * 64
    S3_MAX_CONCURRENCY = 40
    S3_MAX_IO_QUEUE = 1000

    def __init__(self, client, stage):
        self.divio_client = client

        # Migration data
        self.stage = stage

        # Project settings
        project_home = utils.get_project_home()
        aldryn_settings = utils.get_aldryn_project_settings(project_home)
        website_id = aldryn_settings['id']
        self.website_slug = aldryn_settings['slug']

        # S3 config
        aws_config = utils.get_aws_s3_config(client, stage, website_id)
        s3_resource = boto3.resource(
            's3', aws_access_key_id=aws_config['key'],
            aws_secret_access_key=aws_config['secret'],
            config=Config(signature_version='s3v4')
        )
        self.bucket = s3_resource.Bucket(aws_config['bucket'])

        config = TransferConfig(
            multipart_threshold=self.S3_MULTIPART_THRESHOLD,
            multipart_chunksize=self.S3_MULTIPART_CHUNKSIZE,
            max_concurrency=self.S3_MAX_CONCURRENCY,
            max_io_queue=self.S3_MAX_IO_QUEUE,
        )
        self.s3_manager = create_transfer_manager(
            s3_resource.meta.client, config
        )

        # Folder config
        local_data_path = os.path.join(project_home, self.DATA_FOLDER)
        self.media_path = os.path.join(local_data_path, self.PREFIX)
        self.remote_data_path = '/{}'.format(self.DATA_FOLDER)

        # Docker machine
        self.docker_compose = utils.get_docker_compose_cmd(project_home)

        # Preconditions
        self.validate()

    def validate(self):
        """Validates pre-conditions"""
        docker_compose_config = utils.DockerComposeConfig(self.docker_compose)

        if not docker_compose_config.has_volume_mount(
                'web', self.remote_data_path
        ):
            self.fail('No mount for /data folder found')

    def fail(self, msg=' error!'):
        click.secho(msg)
        sys.exit(1)

    def run(self):
        raise NotImplementedError

    def make_e_tag(self, file_path):
        with open(file_path, "rb") as local_file:
            return hashlib.md5(local_file.read()).hexdigest()

    def file_matches_e_tag(self, file_path, e_tag):
        # e_tag holds the md5 for the file contents, wrapped in quotes
        return e_tag.strip('"') == self.make_e_tag(file_path)


class PullS3MediaCommand(BaseS3SyncCommand):

    def __init__(self, client, stage):
        super(PullS3MediaCommand, self).__init__(client, stage)

        self.to_download = set()
        self.to_remove = []
        self.already_in_sync = set()

    def prepare_download(self):
        click.secho(' ---> Preparing download', nl=False)
        start_preparation = time()
        for key in self.bucket.objects.all():
            key_string = str(key.key)
            key_path = os.path.join(self.media_path, key_string)
            if not os.path.exists(key_path):
                self.to_download.add(key_string)
            else:
                if self.file_matches_e_tag(key_path, key.e_tag):
                    self.already_in_sync.add(key_string)
                else:
                    self.to_download.add(key_string)
        click.echo(' [{}s]'.format(int(time() - start_preparation)))

    def download_from_s3(self):
        click.secho(
            ' ---> Downloading {} files'.format(len(self.to_download)),
            nl=False,
        )
        start_download = time()
        downloads = []
        downloaded_count = 0
        for key in self.to_download:
            key_dir = os.path.join(self.media_path, *key.split("/")[:-1])
            if not os.path.exists(key_dir):
                os.makedirs(key_dir)
            key_path = os.path.join(key_dir, key.split("/")[-1])
            downloads.append(
                self.s3_manager.download(
                    self.bucket.name,
                    key,
                    str(key_path),
                )
            )
            for download in downloads:
                # Wait for the task to finish
                download.result()
                downloaded_count += 1
        click.echo(' [{}s]'.format(int(time() - start_download)))

        # Fix permissions whenever needed
        self.fix_permissions()

    def fix_permissions(self):
        if 'linux' in sys.platform:
            # On Linux, Docker typically runs as root, so files and folders
            # created from within the container will be owned by root. As a
            # workaround, make the folder permissions more permissive, to
            # allow the invoking user to create files inside it.
            check_call(
                self.docker_compose(
                    'run', '--rm', 'web',
                    'chown', '-R', str(os.getuid()), self.remote_data_path
                )
            )

    def prepare_cleanup(self):
        start_local_check = time()
        media_path_len = len(self.media_path) + 1
        click.secho(' ---> Checking local files', nl=False)

        for (dirpath, dirnames, filenames) in os.walk(self.media_path):
            for filename in filenames:
                local_file_path = os.path.join(dirpath, filename)
                expected_key = local_file_path[media_path_len:]
                if (expected_key not in self.to_download and
                        expected_key not in self.already_in_sync):
                    self.to_remove.append(local_file_path)

        click.echo(' [{}s]'.format(int(time() - start_local_check)))

    def cleanup_local_files(self):
        click.secho(
            ' ---> Do you want to clean up {} unused local files?'.format(
                len(self.to_remove)),
            fg='yellow',
            nl=False,
        )
        if click.confirm(''):
            start_delete = time()
            click.secho(' ---> Deleting local files', nl=False)
            for local_file_path in self.to_remove:
                # Remove file
                os.remove(local_file_path)
                dir_path = os.path.split(local_file_path)[0]
                try:
                    # Remove as many empty dirs as possible
                    os.removedirs(dir_path)
                except OSError:
                    # Not empty
                    pass
            click.echo(' [{}s]'.format(int(time() - start_delete)))

    def run(self):
        click.secho(
            ' ===> Pulling media files from {} {} server'.format(
                self.website_slug,
                self.stage,
            ),
        )

        start_time = time()

        # Download from remote bucket
        self.prepare_download()
        if self.to_download:
            self.download_from_s3()
        else:
            click.secho(' ---- No new files to download')

        # Cleanup local unused files
        self.prepare_cleanup()
        if self.to_remove:
            self.cleanup_local_files()
        else:
            click.secho(' ---- No local files to remove')

        click.secho('Done', fg='green', nl=False)
        click.echo(' [{}s]'.format(int(time() - start_time)))
