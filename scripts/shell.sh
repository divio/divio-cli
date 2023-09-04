#!/bin/bash

# This script creates shims for every Python version configured in
# PYTHON_VERSIONS, adds all created shims to the PATH, and then execs
# into /bin/bash.
# All shims are named "divio" or "divio-$PYTHON_VERSION" (for example
# divio-python3.11 or divio-pypy3) and link to /app/scripts/divio.sh.

DEFAULT_PYTHON_VERSION=python3
SHIM_EXECUTABLE=/app/scripts/divio.sh
SHIM_DIRECTORY=/app/.artifacts/divio-shims/


function create-shim() {
    # args:
    #   $1: interpreter name like "python3.10" or "pypy3" and 
    #   $2: shim name (optional)

    if [ -z "$2" ]; then
        shim_name="divio-$1"
    else
        shim_name=$2
    fi

    shim_path="$SHIM_DIRECTORY/$shim_name"

    if [ -f "$shim_path" ]; then
        return
    fi

    ln -s $SHIM_EXECUTABLE $shim_path 
}


# create shim directory if not present
if [ ! -e "$SHIM_DIRECTORY" ]; then
    mkdir -p $SHIM_DIRECTORY
fi

# create default shim
echo "divio available"
create-shim $DEFAULT_PYTHON_VERSION divio

# create shims from $PYTHON_VERSIONS
for version in ${PYTHON_VERSIONS//,/ }; do
    interpreter_path=$(which $version)

    if [ -z "$interpreter_path" ]; then
        echo "WARNING: No Python interpreter named \"$version\" found"
        continue
    fi

    create-shim $version

    echo "divio-$version available"
done

# launch shell
export PATH=$SHIM_DIRECTORY:$PATH
exec /bin/bash
