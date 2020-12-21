#!/usr/bin/env python
import sys
import setuptools


with open('requirements.txt') as f:
    requirements = f.read().splitlines()

if sys.platform == 'win32':
    with open('requirements-windows.txt') as f:
        requirements += f.read().splitlines()


if __name__ == "__main__":

    setuptools.setup(
        name='divio-cli',
        install_requires=requirements,
        setup_requires=['setuptools_scm'],
        use_scm_version ={
            "write_to":"divio_cli/version.py"
        }
    )
