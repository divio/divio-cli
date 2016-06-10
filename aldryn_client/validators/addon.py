from __future__ import unicode_literals

import shutil
import imp
import time
import os

import click

from .. import settings
from .. import messages
from ..utils import silence_stderr, create_temp_dir
from .common import validate_package_config, load_config


ADDON_REQUIRED_CONFIG_KEYS = (
    'package-name',
)


def validate_aldryn_config_py(path):
    aldryn_config_path = os.path.join(path, 'aldryn_config.py')
    if os.path.exists(aldryn_config_path):
        temp_dir = create_temp_dir()
        try:
            shutil.copy(aldryn_config_path, temp_dir)
            temp_path = os.path.join(temp_dir, 'aldryn_config.py')
            try:
                with silence_stderr():
                    # suppressing RuntimeWarning: Parent module 'aldryn_config'
                    # not found while handling absolute import

                    # randomizing source name
                    source = 'aldryn_config.config_{}'.format(int(time.time()))
                    module = imp.load_source(source, temp_path)

                # checking basic functionality of the Form
                form = module.Form({})
                form.is_valid()

            except Exception:
                # intentionally catch every exception
                import traceback
                click.secho(
                    "An error occurred during validating 'aldryn_config.py'. "
                    "Please check the exception below:\n",
                    fg='red'
                )
                raise click.ClickException(traceback.format_exc())
        finally:
            shutil.rmtree(temp_dir)


def validate_addon(path=None):
    setup_py_path = os.path.join(path or '.', 'setup.py')
    if not os.path.exists(setup_py_path):
        raise click.ClickException(
            messages.FILE_NOT_FOUND.format(setup_py_path)
        )

    config = load_config(settings.ADDON_CONFIG_FILENAME, path)
    validate_aldryn_config_py(path)
    validate_package_config(config, ADDON_REQUIRED_CONFIG_KEYS, path)
