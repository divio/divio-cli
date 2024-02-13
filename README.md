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

⚠️ **For Windows users**: Make sure you have added Python to PATH during installation, otherwise you must add it manually for the divio-cli commands to function properly.

# Using the CLI

See [Divio developer handbook: How to use the Divio command-line interface](https://docs.divio.com/en/latest/how-to/local-cli/)


# Support for docker-compose 1 and 2

The CLI supports version 1 (`docker-compose`) and version 2 (`docker compose`) of the command invocation and is using the new version 2 by default.

You can opt-in to still use the old version 1 command by updating your CLI global settings in `~/.aldryn` and add a new setting called `docker-compose` with the value `["docker-compose"]`:

```json
{"update_check_timestamp": 1234567890, "docker-compose": ["docker-compose"]}
```




# Testing

The test suite is split into two categories: unit tests and integration tests. Unit tests run completely locally, so no previous setup is required. Integration tests run against the actual Divio infrastructure, so setup of a Divio project is required.
In order to run the test suite, you have to have [GNU Make](https://www.gnu.org/software/make/) and [GNU Bash](https://www.gnu.org/software/bash/) on your system. The integration tests also require [Docker Compose](https://docs.docker.com/compose/).

Both test categories take optional arguments like `TOX_ARGS` and `PYTEST_ARGS`:

```bash
make test TOX_ARGS="-e python.11" PYTEST_ARGS="-s"
```

To clear all local state run:

```bash
make clean
```

## Unit tests

These do not require external communication and can be run with the following command:

```bash
make test
```

## Integration tests

These do require a more involved setup and will trigger actions on a real project.
It is recommended to use a project on [control.dev.aldryn.net](https://control.dev.aldryn.net/) because it requires no control panel running locally, and is what the CI pipeline does.

The CI uses [ci-test-project-do-not-delete](https://control.dev.aldryn.net/o/crce57yucffnjhb63yldeohmru/app/nxldpjkvbzggzh6xzvkqv4j3je/) project.
**DO NOT USE THIS PROJECT FOR YOUR LOCAL TESTING!** The project is reserved for CI testing. Create your own project and replicate the CI project configuration.

To run the integration test suite, run:

```bash
make test_integration
```

The first run will fail, but will create an empty `.env` file. Configure your test project there.
You can take a look at the variables tab in the [CI Settings](https://gitlab.com/divio/cloud/control-panel/-/settings/ci_cd) as a starting point.

## Linting

To run the linter, run the following command:

```bash
make lint
```

## Creating a release

1. Checkout a new branch for the new version - `release-X.X.X`
2. Update the changelog.
3. Merge the branch (after approval).
4. Tag master with the release number `X.X.X` and `git push origin <tagname>`

The pipeline will then take care of the release.
