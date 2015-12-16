import os

import click

from .. import settings
from .common import validate_package_config, load_config


BOILERPLATE_REQUIRED_FILES = (
    'templates/base.html',
)

BOILERPLATE_REQUIRED_CONFIG_KEYS = (
    'package-name',
    'identifier',
    'version',
    'templates',
)


def validate_templates(config):
    data = config.get('templates', [])
    if isinstance(data, (list, tuple)):
        for template in data:
            if not isinstance(template, (list, tuple)) or len(template) != 2:
                return (
                    'Templates must be a list/tuple of lists/tuples '
                    'with two items each.'
                )


def validate_protected_files(config, path):
    protected_files = config.get('protected', [])
    if not isinstance(protected_files, (list, tuple)):
        return ['Protected files setting must be a list or a tuple.']

    errors = []
    for fname in protected_files:
        fpath = os.path.join(path, fname)
        if not fpath.endswith('*') and not os.path.exists(fpath):
            errors.append('Protected file "{}" not found'.format(fname))

    return errors


def validate_boilerplate_config(config, path):
    missing_files = []
    for required_file in BOILERPLATE_REQUIRED_FILES:
        fpath = os.path.join(path, required_file)
        if not os.path.exists(fpath):
            missing_files.append(fpath)

    if missing_files:
        click.secho(
            'The following required files were not found:\n{}'.format(
            '\n'.join(missing_files)), fg='yellow')

    errors = validate_package_config(
        config=config,
        required_keys=BOILERPLATE_REQUIRED_CONFIG_KEYS,
        config_path=path
    )

    template_validation_error = validate_templates(config)
    if template_validation_error:
        errors.append(template_validation_error)

    protected_files_validation_errors = validate_protected_files(config, path)
    errors.extend(protected_files_validation_errors)

    if errors:
        message = 'The following errors happened during validation:'
        message = '{}\n - {}'.format(message, '\n - '.join(errors))
        raise click.ClickException(message)

    return True


def validate_boilerplate(path=None):
    config = load_config(settings.BOILERPLATE_CONFIG_FILENAME, path)
    return validate_boilerplate_config(config, path)
