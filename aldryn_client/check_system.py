# -*- coding: utf-8 -*-
import os
import subprocess
from collections import OrderedDict

import click

from . import utils

ALL_CHECKS = OrderedDict([
    ('git', ('Git', ['git', '--version'])),
    ('docker-client', ('Docker Client', ['docker', '--version'])),
    ('docker-machine', ('Docker Machine', ['docker-machine', '--version'])),
    ('docker-compose', ('Docker Compose', ['docker-compose', '--version'])),
    ('docker-server', ('Docker Server Connectivity', ['docker', 'ps'])),
])


def check_command(command):
    error_msg = None
    try:
        utils.check_call(command, catch=False, silent=True)
    except OSError as exc:
        if exc.errno == os.errno.ENOENT:
            error_msg = 'executable {} not found'.format(command[0])
        else:
            error_msg = (
                'unknown error while trying to run {}: {}'
                .format(command, exc.message)
            )
    except subprocess.CalledProcessError as exc:
        error_msg = exc.output or str(exc)
    return error_msg


def check_requirements(checks=None):
    if checks is None:
        checks = ALL_CHECKS.keys()

    for check in checks:
        check_name, cmd = ALL_CHECKS[check]
        yield check, check_name, check_command(cmd)


def check_requirements_human(checks=None, silent=False):
    errors = []

    for check, check_name, error in check_requirements(checks):
        if error:
            errors.append((check_name, error))
        if not silent:
            is_windows = utils.is_windows()
            if error:
                symbol = ' ERR ' if is_windows else ' ✖  '
                color = 'red'
            else:
                symbol = ' OK  ' if is_windows else ' ✓  '
                color = 'green'
            click.secho(symbol, fg=color, nl=False)
            click.secho(check_name)

    if errors and not silent:
        click.secho('\nThe following errors occurred:', fg='red')
        for check_name, msg in errors:
            click.secho(' {}:\n > {}'.format(check_name, msg))

    return not bool(errors)
