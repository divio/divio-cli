import json
import os
import tempfile
import subprocess
import tarfile
from StringIO import StringIO

import click

from .. import settings
from ..utils import dev_null, tar_add_stringio, get_package_version
from ..validators.addon import validate_addon
from ..validators.common import load_config, get_license


def package_addon(path):
    temp_dir = tempfile.mkdtemp(prefix='tmp_aldryn_client_')
    with dev_null() as devnull:
        subprocess.check_call(
            ['python', 'setup.py', 'sdist', '-d', temp_dir],
            cwd=path, stdout=devnull,
        )
    for filename in os.listdir(temp_dir):
        if filename.endswith('.tar.gz'):
            return os.path.join(temp_dir, filename)

    raise click.ClickException('Packaged addon could not be found')


def add_meta_files(tar, path):
    # addon.json
    addon_json = load_config(settings.ADDON_CONFIG_FILENAME, path)
    addon_json_fileobj = StringIO()
    json.dump(addon_json, addon_json_fileobj)
    tar_add_stringio(tar, addon_json_fileobj, 'addon.json')

    # aldryn_config.py
    try:
        with open(os.path.join(path, 'aldryn_config.py')) as fobj:
            tar_add_stringio(tar, StringIO(fobj.read()), 'aldryn_config.py')
    except (OSError, IOError):
        click.secho(
            'Warning: Aldryn config file \'aldryn_config.py\' not found. '
            'Your app will not have any configurable settings.'
        )

    # license
    license_filepath = get_license(path)
    if license_filepath:
        tar.add(license_filepath, 'LICENSE.txt')

    # version
    version_fobj = StringIO(get_package_version(path))
    info = tarfile.TarInfo(name='VERSION')
    info.size = len(version_fobj.getvalue())
    tar.addfile(info, fileobj=version_fobj)


def create_addon_archive(path):
    data_fobj = StringIO()

    with tarfile.open(mode='w:gz', fileobj=data_fobj) as tar:
        add_meta_files(tar, path)
        packaged_addon = package_addon(path)
        tar.add(packaged_addon, arcname='package.tar.gz')

    data_fobj.seek(0)
    return data_fobj


def upload_addon(client, path=None):
    path = path or '.'
    validate_addon(path)
    archive_obj = create_addon_archive(path)
    return client.upload_addon(archive_obj)
