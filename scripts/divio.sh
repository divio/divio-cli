#!/bin/bash
set -e

# This script is the main entry point for all shims created by
# /app/scripts/shell.sh.

DEFAULT_PYTHON_VERSION=python3
PACKAGE_PATH=/app
VENV_ROOT=/app/.artifacts/divio-venvs


# find interpreter
shim_name=$(basename $0)
interpreter=$(echo $shim_name | cut -d "-" -f 2-)
venv_path=$VENV_ROOT/$interpreter

if [ "$interpreter" == "divio" ]; then
    interpreter=$DEFAULT_PYTHON_VERSION
fi

# create venv root if not present
if [ ! -e "$VENV_ROOT" ]; then
    mkdir -p $VENV_ROOT
fi

# create venv if not present
if [ ! -e "$venv_path" ]; then
    echo "creating virtual environment for \"$shim_name\""

    $interpreter -m venv $venv_path
    source $venv_path/bin/activate
    pip install -e $PACKAGE_PATH
fi

# jump to actual executable
exec $venv_path/bin/divio $@
