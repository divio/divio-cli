import importlib.machinery
import importlib.util
import os
import shutil
import time

import click

from divio_cli.exceptions import DivioException

from .. import messages, settings
from ..utils import create_temp_dir, silence_stderr
from .common import load_config, validate_package_config


ADDON_REQUIRED_CONFIG_KEYS = ("package-name",)


def load_source(modname, filename):
    """Compatibility function to replace usage of `imp` module."""
    loader = importlib.machinery.SourceFileLoader(modname, filename)
    spec = importlib.util.spec_from_file_location(
        modname, filename, loader=loader
    )
    module = importlib.util.module_from_spec(spec)
    # The module is always executed and not cached in sys.modules.
    # Uncomment the following line to cache the module.
    # sys.modules[module.__name__] = module
    loader.exec_module(module)
    return module


def validate_aldryn_config_py(path):
    aldryn_config_path = os.path.join(path, "aldryn_config.py")
    if os.path.exists(aldryn_config_path):
        temp_dir = create_temp_dir()
        try:
            shutil.copy(aldryn_config_path, temp_dir)
            temp_path = os.path.join(temp_dir, "aldryn_config.py")
            try:
                with silence_stderr():
                    # suppressing RuntimeWarning: Parent module 'aldryn_config'
                    # not found while handling absolute import

                    # randomizing source name
                    source = f"aldryn_config.config_{int(time.time())}"
                    module = load_source(source, temp_path)

                # checking basic functionality of the Form
                form = module.Form({})
                form.is_valid()

            except Exception:
                # intentionally catch every exception
                import traceback

                click.secho(
                    "An error occurred during validating 'aldryn_config.py'. "
                    "Please check the exception below:\n",
                    fg="red",
                    err=True,
                )
                raise DivioException(traceback.format_exc())
        finally:
            shutil.rmtree(temp_dir)


def validate_addon(path=None):
    setup_py_path = os.path.join(path or ".", "setup.py")
    if not os.path.exists(setup_py_path):
        raise DivioException(messages.FILE_NOT_FOUND.format(setup_py_path))

    config = load_config(settings.ADDON_CONFIG_FILENAME, path)
    validate_aldryn_config_py(path)
    validate_package_config(config, ADDON_REQUIRED_CONFIG_KEYS, path)
