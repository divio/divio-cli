# -*- coding: utf-8 -*-
import os
import subprocess
from collections import OrderedDict
from sys import platform

import click

from . import utils


def errorhint_docker_server():
    """This function provides additional hints and suggestions if the `docker ps` command fails."""
    errors = []
    if platform == "linux" or platform == "linux2":
        if not os.access("/var/run/docker.sock", os.R_OK):
            errors.append("No read permissions to /var/run/docker.sock. docker must be able to operate as your user without root permissions. Check the docker installation guide: https://docs.docker.com/engine/installation/linux/")
    return errors


ALL_CHECKS = OrderedDict([
    ('git', ('Git', ['git', '--version'], None)),
    ('docker-client', ('Docker Client', ['docker', '--version'], None)),
    ('docker-machine', ('Docker Machine', ['docker-machine', '--version'], None)),
    ('docker-compose', ('Docker Compose', ['docker-compose', '--version'], None)),
    ('docker-server', ('Docker Server Connectivity', ['docker', 'ps'], errorhint_docker_server)),
])

    

def check_command(command):
    errors = []
    try:
        utils.check_call(command, catch=False, silent=True)
    except OSError as exc:
        if exc.errno == os.errno.ENOENT:
            errors.append('executable {} not found'.format(command[0]))
        else:
            errors.append(
                'unknown error while trying to run {}: {}'
                .format(command, exc.message)
            )
    except subprocess.CalledProcessError as exc:
        errors.append(exc.output or str(exc))
    return errors


def check_requirements(checks=None):
    if checks is None:
        checks = ALL_CHECKS.keys()

    for check in checks:
        check_name, cmd, error_hint = ALL_CHECKS[check]
        errors = check_command(cmd)
        if errors and error_hint:
            errors += error_hint()
        yield check, check_name, errors


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
        for check_name, msgs in errors:
            click.secho(' {}:'.format(check_name))
            for msg in msgs:
                click.secho(' > {}'.format(msg))

    return not bool(errors)
