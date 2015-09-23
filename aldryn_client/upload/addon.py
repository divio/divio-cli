import os
import subprocess
import tarfile
from io import StringIO

import click

from .. import settings
from ..utils import (
    dev_null, tar_add_stringio, get_package_version, create_temp_dir,
)
from ..validators.addon import validate_addon
from .common import add_meta_files


def package_addon(path):
    temp_dir = create_temp_dir()
    with dev_null() as devnull:
        subprocess.check_call(
            ['python', 'setup.py', 'sdist', '-d', temp_dir],
            cwd=path, stdout=devnull,
        )
    for filename in os.listdir(temp_dir):
        if filename.endswith('.tar.gz'):
            return os.path.join(temp_dir, filename)

    raise click.ClickException('Packaged addon could not be found')


def add_addon_meta_files(tar, path):
    # aldryn_config.py
    try:
        with open(os.path.join(path, 'aldryn_config.py')) as fobj:
            tar_add_stringio(tar, StringIO(fobj.read()), 'aldryn_config.py')
    except (OSError, IOError):
        click.secho(
            'Warning: Aldryn config file \'aldryn_config.py\' not found. '
            'Your app will not have any configurable settings.'
        )

    # version
    version_fobj = StringIO(get_package_version(path))
    info = tarfile.TarInfo(name='VERSION')
    info.size = len(version_fobj.getvalue())
    tar.addfile(info, fileobj=version_fobj)


def create_addon_archive(path):
    data = StringIO()

    with tarfile.open(mode='w:gz', fileobj=data) as tar:
        add_meta_files(tar, path, settings.ADDON_CONFIG_FILENAME)
        add_addon_meta_files(tar, path)
        packaged_addon = package_addon(path)
        tar.add(packaged_addon, arcname='package.tar.gz')

    data.seek(0)
    return data


def upload_addon(client, path=None):
    path = path or '.'
    validate_addon(path)
    archive_obj = create_addon_archive(path)
    return client.upload_addon(archive_obj)
