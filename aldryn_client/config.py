import json
import time
import os
from distutils.version import StrictVersion

import click

from . import utils, __version__


class Config(object):
    config_name = '.aldryn'

    def __init__(self):
        super(Config, self).__init__()
        home = os.path.expanduser('~')
        self.config_path = os.path.join(home, self.config_name)
        self.read()

    def read(self):
        try:
            with open(self.config_path, 'r') as fh:
                config = json.load(fh)
        except IOError:
            # file doesn't exist
            config = {}
        except ValueError:
            # invalid config
            config = {}
        self.config = config

    def save(self):
        with open(self.config_path, 'w+') as fh:
            json.dump(self.config, fh)

    def check_for_updates(self):
        """check daily for updates"""
        if self.config.get('disable_update_check', False):
            return

        timestamp_key = 'update_check_timestamp'
        version_key = 'update_check_version'

        last_checked = self.config.get(timestamp_key, None)
        now = int(time.time())
        current_version = StrictVersion(__version__)

        if not last_checked or last_checked < now - (60 * 60 * 24):
            # try to access PyPi to get the latest available version
            newest_version, _ = utils.get_latest_version_from_pypi()

            if newest_version:
                if newest_version > current_version:
                    self.config[version_key] = str(newest_version)
                self.config[timestamp_key] = now
                self.save()
            elif newest_version is False:
                # fail silently, nothing the user can do about this
                self.config.pop(version_key, None)

        newer_version_string = self.config.get(version_key, None)
        if newer_version_string:
            newer_version = StrictVersion(newer_version_string)
            if newer_version == current_version:
                self.config.pop(version_key)
            else:
                click.secho(
                    "New version ({version}) available on PyPi. Update "
                    "now using 'pip install aldryn-client=={version}'"
                    .format(version=newer_version),
                    fg='yellow'
                )
