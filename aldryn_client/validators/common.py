import json
import re
import os

import click


from .. import messages


VALID_LICENSE_FILENAMES = (
    'LICENSE.txt',
    'LICENSE',
    'license.txt',
    'license',
)

FILENAME_BASIC_RE = re.compile(
    r'^[a-zA-Z0-9_@]+[a-zA-Z0-9._@-]*\.[a-zA-Z0-9]{1,23}$'
)

ALLOWED_EXTENSIONS = (
    '.css',
    '.gif',
    '.htc',
    '.htm',
    '.html',
    '.ico',
    '.jpeg',
    '.jpg',
    '.js',
    '.json',
    '.less',
    '.map',
    '.png',
    '.rb',
    '.sass',
    '.scss',
    '.svg',
    '.webm',
    # font formats
    '.eot',
    '.ttf',
    '.woff',
    '.woff2',
    '.otf',
    # text formats
    '.txt',
    '.md',
    '.rst',
    # document formats
    '.pdf',
    '.ps',
    '.djv',
    '.djvu',
    '.doc',
    '.docx',
    '.ppt',
    '.pptx',
    '.xls',
    '.xlsx',
)


def is_valid_file_name(name):
    if not FILENAME_BASIC_RE.match(name):
        return False
    ext = os.path.splitext(name)[-1]
    if ext not in ALLOWED_EXTENSIONS:
        return False
    return True


def get_license(path):
    for fname in VALID_LICENSE_FILENAMES:
        fpath = os.path.join(path, fname)
        if os.path.exists(fpath):
            return fpath


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

    if not get_license(config_path):
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
