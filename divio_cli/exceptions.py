from __future__ import annotations

import sys
from enum import IntEnum

import attr
import click

from divio_cli import settings


DOT_DIVIO_FILE_NOT_FOUND = (
    "Divio Cloud configuration file '{}' or '{}' could not be found!\n"
    "Please make sure you're in a Divio Cloud project folder and the "
    "file exists.\n\n"
    "You can create a new configuration file for an existing project "
    "with the `divio app configure` command.".format(
        settings.ALDRYN_DOT_FILE, settings.DIVIO_DOT_FILE
    )
)


class ExitCode(IntEnum):
    SUCCESS = 0
    GENERIC_ERROR = 1


@attr.s(auto_attribs=True)
class DivioException(click.ClickException):
    """Base class for all known exceptions that shouldn't trigger a sentry report."""

    message: str | None = None
    exit_code: ExitCode = ExitCode.GENERIC_ERROR
    fg: str | None = "red"

    def show(self):
        if self.message:
            click.secho(self.format_message(), fg=self.fg, err=True)
        self.exit_if_needed()

    def exit_if_needed(self):
        if self.exit_code != 1:
            sys.exit(self.exit_code)

    def __str__(self) -> str:
        return self.format_message() or ""


class DivioWarning(DivioException):
    """A warning printed in yellow with a success exit code."""

    def __init__(self, message):
        super().__init__(message, fg="yellow", exit_code=ExitCode.SUCCESS)


class ConfigurationNotFound(DivioException):
    def __init__(self):
        super().__init__(message=DOT_DIVIO_FILE_NOT_FOUND)


class EnvironmentDoesNotExist(DivioException):
    def __init__(self, environment):
        super().__init__(
            f"Environment with the name '{environment}' does not exist."
        )


class DockerComposeDoesNotExist(DivioException):
    def __init__(self, message=""):
        if message:
            message = f"{message}: "
        super().__init__(f"{message}docker-compose.yml does not exist.")


class ApplicationUUIDNotFoundException(DivioException):
    def __init__(self, message="No Application UUID or Project ID was found"):
        super().__init__(message)
