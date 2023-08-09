from unittest.mock import Mock

import pytest

from divio_cli.exceptions import (
    DOT_DIVIO_FILE_NOT_FOUND,
    ConfigurationNotFound,
    DivioException,
    DivioStepException,
    DivioWarning,
    DockerComposeDoesNotExist,
    EnvironmentDoesNotExist,
    ExitCode,
)


@pytest.mark.parametrize("exit_code", [0, 1, 127])
def test_exception_status_code(monkeypatch, exit_code):
    exit_mock = Mock()
    monkeypatch.setattr("divio_cli.exceptions.sys.exit", exit_mock)

    ex = DivioException(exit_code=exit_code)
    ex.show()

    if exit_code == 1:
        exit_mock.assert_not_called()
    else:
        exit_mock.assert_called_once_with(exit_code)


def test_divio_exception():
    ex = DivioException("message")
    assert ex.format_message() == "message"
    assert ex.fg == "red"
    assert ex.exit_code == ExitCode.GENERIC_ERROR

    ex = DivioException("message", fg="green", exit_code=ExitCode.SUCCESS)
    assert ex.format_message() == "message"
    assert ex.fg == "green"
    assert ex.exit_code == ExitCode.SUCCESS


def test_divio_warning():
    ex = DivioWarning("warning")
    assert ex.format_message() == "warning"
    assert ex.fg == "yellow"
    assert ex.exit_code == ExitCode.SUCCESS


def test_step_exception():
    ex = DivioStepException("step")
    assert ex.format_message() == " error!\nstep"
    assert ex.fg == "red"
    assert ex.exit_code == ExitCode.GENERIC_ERROR

    assert DivioStepException("step", fg="green").fg == "green"


def test_environment_does_not_exist():
    ex = EnvironmentDoesNotExist("env")
    assert ex.message == "Environment with the name 'env' does not exist."
    assert ex.fg == "red"
    assert ex.exit_code == ExitCode.GENERIC_ERROR


def test_docker_compose_does_not_exist():
    ex = DockerComposeDoesNotExist()
    assert ex.message == "docker-compose.yml does not exist."
    assert ex.fg == "red"
    assert ex.exit_code == ExitCode.GENERIC_ERROR

    ex = DockerComposeDoesNotExist("During test")
    assert ex.message == "During test: docker-compose.yml does not exist."


def test_configuration_not_found():
    ex = ConfigurationNotFound()
    assert ex.message == DOT_DIVIO_FILE_NOT_FOUND
    assert ex.fg == "red"
    assert ex.exit_code == ExitCode.GENERIC_ERROR
