Divio CLI - Command-line interface to the Divio Cloud
=====================================================

[![PyPI Version](https://img.shields.io/pypi/v/divio-cli.svg)](https://pypi.python.org/pypi/divio-cli)
![PyPI Downloads](https://img.shields.io/pypi/dm/divio-cli.svg)
![Wheel Support](https://img.shields.io/pypi/wheel/divio-cli.svg)
[![License](https://img.shields.io/pypi/l/divio-cli.svg)](https://github.com/divio/divio-cli/blob/master/LICENSE.txt)

# Installing

```bash
pip install divio-cli
```

# Using the CLI

See [Divio Support: How to use the Divio command-line interface](http://support.divio.com/local-development/divio-shell/divio-cli-reference)


# Support for docker-compose 1 and 2

The CLI supports version 1 (`docker-compose`) and version 2 (`docker compose`) of the command invokation. At the time of this writing, the CLI will use v1 command invokation by default because v2 is still in beta. This will likely change in the future.

You can opt-in to use the new command by updating your CLI global settings in `~/.aldryn` and add a new setting called `docker-compose` with the value `["docker", "compose"]`.


# Testing

We have two kinds of tests. Small and quick unit tests and the more complex and involved integration tests.

## Unit tests

These do not require external communication and can be run with the following command:

```bash
tox -- -m "not integration"
```

## Integration tests

These to require a more involved setup and will trigger actions on a real project. You have to provide the project name and your user must be logged in into divio cloud.

You might get asked to provide authentication information during the test, depending on your setup.

```bash
tox --  -m "integration" --test_project_name <NAME_OF_A_PROJECT_FOR_TESTING>
```
