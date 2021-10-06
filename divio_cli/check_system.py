# -*- coding: utf-8 -*-
import errno
import os
import subprocess
import sys
from collections import OrderedDict

import click

from . import cloud, utils
from .settings import DOCKER_TEST_IMAGE


ERROR = 1
WARNING = 0


class Check(object):
    name = None
    command = None
    error_level = ERROR

    def run_check(self):
        errors = []
        try:
            utils.check_call(self.command, catch=False, silent=True)
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                errors.append(
                    "Executable {} not found".format(self.command[0])
                )
            else:
                msg = "Command '{}' returned non-zero exit status {}".format(
                    self.fmt_command(), exc.errno
                )
                if hasattr(exc, "strerror"):
                    msg += ": {}".format(exc.strerror)

                if not msg[-1] == ".":
                    msg += "."
                errors.append(msg)
        except subprocess.CalledProcessError as exc:
            errors += self.fmt_exception(exc)
        return errors

    def fmt_command(self):
        return " ".join(self.command)

    def fmt_exception(self, exc):
        command_output = exc.output

        if command_output:
            message = command_output
        else:
            message = "Command '{}' returned non-zero exit status {}".format(
                self.fmt_command(), exc.returncode
            )

        return [message]


class LoginCheck(Check):
    name = "Login"

    def run_check(self):
        client = cloud.CloudClient(cloud.get_endpoint())
        success, msg = client.check_login_status()
        if not success:
            return [msg]


class GitCheck(Check):
    name = "Git"
    command = ("git", "--version")


class DockerClientCheck(Check):
    name = "Docker Client"
    command = ("docker", "--version")


class DockerComposeCheck(Check):
    name = "Docker Compose"
    command = ("docker", "compose", "version")

    def run_check(self):
        """
        Modified run_check method to check for both old and new docker
        compose versions.
        """
        errors = []
        try:
            try:
                utils.check_call(self.command, catch=False, silent=True)
            except (OSError, subprocess.CalledProcessError):
                # Check for the old version
                utils.check_call(
                    ("docker-compose", "--version"), catch=False, silent=True
                )
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                errors.append(
                    "Neither `docker compose` nor `docker-compose` found."
                )
            msg = "Command '{}' returned non-zero exit status {}".format(
                self.fmt_command(), exc.errno
            )
            if hasattr(exc, "strerror"):
                msg += ": {}".format(exc.strerror)

            if not msg[-1] == ".":
                msg += "."
            errors.append(msg)
        except subprocess.CalledProcessError as exc:
            errors += self.fmt_exception(exc)
        return errors


def get_engine_down_error():
    return (
        "Couldn't connect to Docker daemon. Please start the docker service."
    )


class DockerEngineBaseCheck(Check):
    def fmt_exception(self, exc):
        errors = super(DockerEngineBaseCheck, self).fmt_exception(exc)
        if exc.returncode == 125:
            errors.append(get_engine_down_error())
        return errors


class DockerEngineCheck(DockerEngineBaseCheck):
    name = "Docker Engine Connectivity"
    command = ("docker", "run", "--rm", DOCKER_TEST_IMAGE, "true")

    def fmt_exception(self, exc):
        errors = super(DockerEngineCheck, self).fmt_exception(exc)
        if not utils.is_windows():
            default_host_path = "/var/run/docker.sock"
            default_host_url = "unix://{}".format(default_host_path)
            current_host_url = os.environ.get("DOCKER_HOST")
            current_host_is_default = current_host_url == default_host_url

            # run additional checks if it user is running default config
            if not current_host_url or current_host_is_default:

                # check if docker socket exists
                if not os.path.exists(default_host_path):
                    errors.append(
                        "Could not find docker engine socket at {}. Please "
                        "make sure your docker engine is setup correctly and "
                        "check the docker installation guide: "
                        "https://docs.docker.com/engine/installation/".format(
                            default_host_path
                        )
                    )

                elif not os.access(default_host_path, os.R_OK):
                    # check if docker socket is readable
                    errors.append(
                        "No read permissions on {}. Please make sure the unix "
                        "socket can be accessed without root permissions. "
                        "More information can be found in the docker "
                        "installation guide: https://docs.docker.com/engine/"
                        "installation/linux/ubuntulinux/#create-a-docker-group".format(
                            default_host_path
                        )
                    )

        return errors


class DockerEnginePingCheck(DockerEngineBaseCheck):
    name = "Docker Engine Internet Connectivity"
    command = (
        "docker",
        "run",
        "--rm",
        DOCKER_TEST_IMAGE,
        "ping",
        "-c",
        "1",  # stop after one packet response
        "-W",
        "5",  # timeout of 5 seconds
        "8.8.8.8",
    )

    def fmt_exception(self, exc):
        errors = super(DockerEnginePingCheck, self).fmt_exception(exc)
        errors.append(
            "The 'ping' command inside docker is not able to ping "
            "8.8.8.8. This might be due to missing internet connectivity, "
            "a firewall or a network configuration problem."
        )
        return errors


class DockerEngineDNSCheck(DockerEngineBaseCheck):
    name = "Docker Engine DNS Connectivity"
    command = (
        "docker",
        "run",
        "--rm",
        DOCKER_TEST_IMAGE,
        "sh",
        "-c",  # run in new a shell to avoid problems with timeout
        "timeout 5 nslookup -type=a control.divio.com. || timeout -t 5 nslookup -type=a control.divio.com.",
    )

    def fmt_exception(self, exc):
        errors = super(DockerEngineDNSCheck, self).fmt_exception(exc)
        errors.append(
            "The DNS resolution inside docker is not able to resolve "
            "control.divio.com. This might be due to missing internet "
            "connectivity, a firewall or a network configuration problem."
        )
        return errors


ALL_CHECKS = OrderedDict(
    [
        ("login", LoginCheck),
        ("git", GitCheck),
        ("docker-client", DockerClientCheck),
        ("docker-compose", DockerComposeCheck),
        ("docker-server", DockerEngineCheck),
        ("docker-server-ping", DockerEnginePingCheck),
        ("docker-server-dns", DockerEngineDNSCheck),
    ]
)


def check_requirements(config=None, checks=None):
    if checks is None:
        checks = ALL_CHECKS.keys()

    skip_doctor_checks = config.get_skip_doctor_checks() if config else []

    for check_key in checks:
        if check_key in skip_doctor_checks:
            continue
        check = ALL_CHECKS.get(check_key)
        if not check:
            click.secho("Invalid check {}".format(check_key), fg="red")
            sys.exit(1)
        errors = check().run_check()
        yield check_key, check.name, errors


def get_prefix(success):
    is_windows = utils.is_windows()
    if success:
        symbol = " OK  " if is_windows else " ✓  "
        color = "green"
    else:
        symbol = " ERR " if is_windows else " ✖  "
        color = "red"
    return symbol, color


def check_requirements_human(config, checks=None, silent=False):
    errors = []

    if config and config.skip_doctor():
        return True

    for check, check_name, error in check_requirements(config, checks):
        if error:
            errors.append((check, check_name, error))
        if not silent:
            symbol, color = get_prefix(not error)
            click.secho(symbol, fg=color, nl=False)
            click.secho(check_name)

    if not errors:
        return True

    if not silent:
        click.secho("\nThe following errors occurred:", fg="red")
        for check, check_name, msgs in errors:
            click.secho("\n {}:".format(check_name))
            for msg in msgs:
                click.secho(" > {}".format(msg))

    max_error_level = max([ALL_CHECKS[e[0]].error_level for e in errors])
    return True if max_error_level == 0 else False
