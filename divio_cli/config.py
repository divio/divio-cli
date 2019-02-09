import json
import os
import time
from distutils.version import StrictVersion

from . import __version__, settings, utils


CONFIG_FILE_NAME = settings.ALDRYN_DOT_FILE
CONFIG_FILE_PATH = os.path.join(os.path.expanduser("~"), CONFIG_FILE_NAME)


class Config(object):
    config_path = CONFIG_FILE_PATH
    config = {}

    def __init__(self):
        super(Config, self).__init__()
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
        installed_version = StrictVersion(__version__)
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
            newest_version = StrictVersion(newest_version_s)
            if newest_version <= installed_version:
                self.config.pop(version_key)
                self.save()
        return dict(
            current=str(__version__),
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
