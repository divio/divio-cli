#!/bin/bash
set -ex

ARCH="`uname -s`"
VENV=venv-$ARCH

# cleanup
rm -rf build dist divio_cli.egg-info $VENV

# create new venv
virtualenv $VENV

# install build requirements
./$VENV/bin/pip install -r requirements.txt -r requirements-build.txt

# package source to wheel and install it
./$VENV/bin/pip install .

# prepare out folder
mkdir -p binary

# create binary
./$VENV/bin/pyinstaller -F -y scripts/entrypoint.py --distpath=binary --hidden-import=_cffi_backend -n divio-$ARCH

# run check
./binary/divio-$ARCH version
