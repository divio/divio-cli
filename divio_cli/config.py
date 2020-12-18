import errno
import json
import os
import time

from . import settings, utils

from setuptools_scm import get_version
from packaging import version



def get_global_config_path():
    old_path = os.path.join(os.path.expanduser("~"), settings.ALDRYN_DOT_FILE)
    if os.path.exists(old_path):
        return old_path
    else:
        return settings.DIVIO_GLOBAL_CONFIG_FILE


class Config(object):
    config = {}

    def __init__(self):
        super(Config, self).__init__()
        self.config_path = get_global_config_path()
        self.read()

    def read(self):
        try:
            with open(self.config_path, "r") as fh:
                config = json.load(fh)
        except IOError:
            # file doesn't exist
            config = {}
        except ValueError:
            # invalid config
            config = {}
        self.config = config

    def save(self):
        # Create folders if they don't exist yet.
        if not os.path.exists(os.path.dirname(self.config_path)):
            try:
                os.makedirs(os.path.dirname(self.config_path))
            except OSError as exc:  # Guard against race condition
                if exc.errno != errno.EEXIST:
                    raise

        with open(self.config_path, "w+") as fh:
            json.dump(self.config, fh)

    def check_for_updates(self, force=False):
        """check for updates daily"""
        if self.config.get("disable_update_check", False) and not force:
            return

        timestamp_key = "update_check_timestamp"
        version_key = "update_check_version"

        last_checked = self.config.get(timestamp_key, None)
        now = int(time.time())
        installed_version = version.parse(get_version())
        pypi_error = None

        if force or not last_checked or last_checked < now - (60 * 60 * 24):
            # try to access PyPI to get the latest available version
            remote_version, pypi_error = utils.get_latest_version_from_pypi()

            if remote_version:
                if remote_version > installed_version:
                    self.config[version_key] = str(remote_version)
                self.config[timestamp_key] = now
                self.save()
            elif remote_version is False:
                # fail silently, nothing the user can do about this
                self.config.pop(version_key, None)

        newest_version_s = self.config.get(version_key, None)
        newest_version = None
        if newest_version_s:
            newest_version = version.parse(newest_version_s)
            if newest_version <= installed_version:
                self.config.pop(version_key)
                self.save()
        return dict(
            current=str(get_version()),
            remote=str(newest_version),
            update_available=(
                newest_version > installed_version if newest_version else False
            ),
            pypi_error=pypi_error,
        )

    def skip_doctor(self):
        return self.config.get("skip_doctor")

    def get_skip_doctor_checks(self):
        checks = self.config.get("skip_doctor_checks")
        if not checks or not isinstance(checks, list):
            return []
        return checks
