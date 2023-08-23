import os
import subprocess
import tarfile
from io import BytesIO, StringIO

import click

from divio_cli.exceptions import DivioException

from .. import settings
from ..utils import (
    create_temp_dir,
    dev_null,
    get_package_version,
    get_subprocess_env,
    tar_add_bytesio,
    tar_add_stringio,
)
from ..validators.addon import validate_addon
from .common import add_meta_files


def package_addon(path):
    temp_dir = create_temp_dir()
    with dev_null() as devnull:
        subprocess.check_call(
            ["python", "setup.py", "sdist", "-d", temp_dir, "--format=gztar"],
            cwd=path,
            stdout=devnull,
            env=get_subprocess_env(),
        )
    for filename in os.listdir(temp_dir):
        if filename.endswith(".tar.gz"):
            return os.path.join(temp_dir, filename)

    raise DivioException("Packaged addon could not be found")


def add_addon_meta_files(tar, path):
    # aldryn_config.py
    try:
        with open(os.path.join(path, "aldryn_config.py"), "rb") as fobj:
            tar_add_bytesio(tar, BytesIO(fobj.read()), "aldryn_config.py")
    except OSError:
        click.secho(
            "Warning: Divio Cloud config file 'aldryn_config.py' not found. "
            "Your app will not have any configurable settings.",
            fg="yellow",
        )

    # version
    tar_add_stringio(tar, StringIO(get_package_version(path)), "VERSION")


def create_addon_archive(path):
    data = BytesIO()

    with tarfile.open(mode="w:gz", fileobj=data) as tar:
        add_meta_files(tar, path, settings.ADDON_CONFIG_FILENAME)
        add_addon_meta_files(tar, path)
        packaged_addon = package_addon(path)
        tar.add(packaged_addon, arcname="package.tar.gz")

    data.seek(0)
    return data


def upload_addon(client, path=None):
    path = path or "."
    validate_addon(path)
    archive_obj = create_addon_archive(path)
    return client.upload_addon(archive_obj)
