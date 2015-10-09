# -*- coding: utf-8 -*-
import os
import subprocess

import click

from .utils import check_call


def check_requirements():
    checks = [
        ('git client', ['git', '--version']),
        ('docker client', ['docker', '--version']),
        ('docker server connection', ['docker', 'ps']),
        ('docker-compose', ['docker-compose', '--version']),
    ]

    errors = []

    for check, cmd in checks:
        error_msg = None
        try:
            check_call(cmd, catch=False, silent=True)
        except OSError as exc:
            if exc.errno == os.errno.ENOENT:
                error_msg = 'executable {} not found'.format(cmd[0])
            else:
                error_msg = (
                    'unknown error while trying to run {}: {}'
                    .format(cmd, exc.message)
                )
        except subprocess.CalledProcessError as exc:
            error_msg = exc.output or str(exc)
        finally:
            if error_msg:
                errors.append((check, error_msg))
                click.secho(' ✖', fg='red', nl=False)
            else:
                click.secho(' ✓', fg='green', nl=False)
            click.secho(' {}'.format(check))

    if errors:
        click.secho('\nThe following errors happened:', fg='red')
        for error, msg in errors:
            click.secho(' {}:\n > {}'.format(error, msg))
