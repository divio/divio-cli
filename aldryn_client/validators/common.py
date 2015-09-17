import json
import os

import click


from .. import messages


VALID_LICENSE_FILENAMES = (
    'LICENSE.txt',
    'LICENSE',
    'license.txt',
    'license',
)


def load_config(fname, path=None):
    config_fpath = os.path.join(path or '.', fname)
    if not os.path.exists(config_fpath):
        raise click.ClickException(
            messages.FILE_NOT_FOUND.format(config_fpath)
        )

    with open(config_fpath) as f:
        try:
            return json.load(f)
        except ValueError:
            raise click.ClickException(
                'Config file could not be loaded: Invalid JSON'
            )


def validate_package_config(config, required_keys, config_path):
    errors = []

    license_exists = any([
        os.path.exists(
            os.path.join(config_path, fname)
        ) for fname in VALID_LICENSE_FILENAMES
    ])

    if not license_exists:
        errors.append(
            'Required LICENSE file not found. Valid names are {}.'.format(
                ', '.join(VALID_LICENSE_FILENAMES)
            )
        )

    for key in required_keys:
        if key not in config:
            errors.append(
                'Required key "{}" not found in config file.'.format(key)
            )

    return errors
