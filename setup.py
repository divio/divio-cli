#!/usr/bin/env python
import sys
import setuptools


with open('requirements.txt') as f:
    requirements = f.read().splitlines()

if sys.platform == 'win32':
    with open('requirements-windows.txt') as f:
        requirements += f.read().splitlines()

from divio_cli import __version__

if __name__ == "__main__":
    setuptools.setup(
        install_requires=requirements,
        setup_requires=['setuptools_scm'],
        version=__version__,
    )
