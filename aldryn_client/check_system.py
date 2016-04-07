# -*- coding: utf-8 -*-
import os
import subprocess
from collections import OrderedDict

import click

from . import utils


class Check(object):
    name = None
    command = None

    def run_check(self):
        errors = []
        try:
            utils.check_call(self.command, catch=False, silent=True)
        except OSError as exc:
            if exc.errno == os.errno.ENOENT:
                errors.append('executable {} not found'.format(self.command[0]))
            else:
                msg = (
                    "Command '{}' returned non-zero exit status {}"
                    .format(self.fmt_command(), exc.errno)
                )
                if hasattr(exc, 'strerror'):
                    msg += ': {}'.format(exc.strerror)

                errors.append(msg)
        except subprocess.CalledProcessError as exc:
            errors += self.fmt_exception(exc)
        return errors

    def fmt_command(self):
        return ' '.join(self.command)

    def fmt_exception(self, exc):
        command_output = exc.output

        if command_output:
            message = command_output
        else:
            message = (
                "Command '{}' returned non-zero exit status {}"
                .format(self.fmt_command(), exc.returncode)
            )

        return [message]


class GitCheck(Check):
    name = 'Git'
    command = ('git', '--version')


class DockerClientCheck(Check):
    name = 'Docker Client'
    command = ('docker', '--version')


class DockerMachineCheck(Check):
    name = 'Docker Machine'
    command = ('docker-machine', '--version')


class DockerComposeCheck(Check):
    name = 'Docker Compose'
    command = ('docker-compose', '--version')


def get_engine_down_error():
    msg = "Couldn't connect to Docker daemon. "
    if utils.is_linux():
        msg += 'Please start the docker service.'
    else:
        msg += 'You might need to run `docker-machine start`.'
    return msg


class DockerEngineBaseCheck(Check):
    def fmt_exception(self, exc):
        errors = super(DockerEngineBaseCheck, self).fmt_exception(exc)
        if exc.returncode == 125:
            errors.append(get_engine_down_error())
        return errors


class DockerEngineCheck(DockerEngineBaseCheck):
    name = 'Docker Engine Connectivity'
    command = ('docker', 'run', '--rm', 'busybox', 'true')

    def fmt_exception(self, exc):
        errors = super(DockerEngineCheck, self).fmt_exception(exc)
        if not utils.is_windows():
            default_host_path = '/var/run/docker.sock'
            default_host_url = 'unix://{}'.format(default_host_path)
            current_host_url = os.environ.get('DOCKER_HOST')
            current_host_is_default = current_host_url == default_host_url

            # run additional checks if it user is running default config
            if not current_host_url or current_host_is_default:

                # check if docker socket exists
                if not os.path.exists(default_host_path):
                    errors.append(
                        'Could not find docker engine socket at {}. Please '
                        'make sure your docker engine is setup correctly and '
                        'check the docker installation guide: '
                        'https://docs.docker.com/engine/installation/'
                        .format(default_host_path)
                    )

                elif not os.access(default_host_path, os.R_OK):
                    # check if docker socket is readable
                    errors.append(
                        'No read permissions on {}. Please make sure the unix '
                        'socket can be accessed without root permissions. '
                        'More information can be found in the docker '
                        'installation guide: https://docs.docker.com/engine/'
                        'installation/linux/ubuntulinux/#create-a-docker-group'
                        .format(default_host_path)
                    )

        return errors


class DockerEngineInternetCheck(DockerEngineBaseCheck):
    name = 'Docker Engine Internet Connectivity'
    command = (
        'docker', 'run', '--rm', 'busybox', 'ping', '-c', '1', '8.8.8.8'
    )

    def fmt_exception(self, exc):
        errors = super(DockerEngineInternetCheck, self).fmt_exception(exc)
        errors.append(
            "The 'ping' command inside docker is not able to ping "
            '8.8.8.8. This might be due to missing internet connectivity, '
            'a firewall or a network configuration problem.'
        )
        return errors


class DockerEngineDNSCheck(DockerEngineBaseCheck):
    name = 'Docker Engine DNS Connectivity'
    command = ('docker', 'run', '--rm', 'busybox',  'nslookup', 'aldryn.com')

    def fmt_exception(self, exc):
        errors = super(DockerEngineDNSCheck, self).fmt_exception(exc)
        errors.append(
            'The DNS resolution inside docker is not able to resolve '
            'aldryn.com. This might be due to missing internet connectivity, '
            'a firewall or a network configuration problem.'
        )
        return errors


ALL_CHECKS = OrderedDict([
    ('git', GitCheck),
    ('docker-client', DockerClientCheck),
    ('docker-machine', DockerMachineCheck),
    ('docker-compose', DockerComposeCheck),
    ('docker-server', DockerEngineCheck),
    ('docker-server-internet', DockerEngineInternetCheck),
    ('docker-server-dns', DockerEngineDNSCheck),
])


def check_requirements(checks=None):
    if checks is None:
        checks = ALL_CHECKS.keys()

    for check_key in checks:
        check = ALL_CHECKS[check_key]()
        errors = check.run_check()
        yield check_key, check.name, errors


def get_prefix(success):
    is_windows = utils.is_windows()
    if success:
        symbol = ' OK  ' if is_windows else ' ✓  '
        color = 'green'
    else:
        symbol = ' ERR ' if is_windows else ' ✖  '
        color = 'red'
    return symbol, color


def check_requirements_human(checks=None, silent=False):
    errors = []

    for check, check_name, error in check_requirements(checks):
        if error:
            errors.append((check_name, error))
        if not silent:
            symbol, color = get_prefix(not error)
            click.secho(symbol, fg=color, nl=False)
            click.secho(check_name)

    if errors and not silent:
        click.secho('\nThe following errors occurred:', fg='red')
        for check_name, msgs in errors:
            click.secho('\n {}:'.format(check_name))
            for msg in msgs:
                click.secho(' > {}'.format(msg))

    return not bool(errors)
