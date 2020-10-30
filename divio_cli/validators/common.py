import json
import os

from .. import exceptions, messages


VALID_LICENSE_FILENAMES = ("LICENSE.txt", "LICENSE", "license.txt", "license")


def get_license(path):
    for fname in VALID_LICENSE_FILENAMES:
        fpath = os.path.join(path, fname)
        if os.path.exists(fpath):
            return fpath


def load_config(fname, path=None):
    config_fpath = os.path.join(path or ".", fname)
    if not os.path.exists(config_fpath):
        raise exceptions.DivioException(
            messages.FILE_NOT_FOUND.format(config_fpath)
        )

    with open(config_fpath) as f:
        try:
            return json.load(f)
        except ValueError:
            raise exceptions.DivioException(
                "Config file could not be loaded: Invalid JSON"
            )


def validate_package_config(config, required_keys, path):
    errors = []

    if not get_license(path):
        errors.append(
            "Required LICENSE file not found. Valid names are {}.".format(
                ", ".join(VALID_LICENSE_FILENAMES)
            )
        )

    for key in required_keys:
        if key not in config:
            errors.append(
                'Required key "{}" not found in config file.'.format(key)
            )

    return errors
