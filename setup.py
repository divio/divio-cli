#!/usr/bin/env python
import sys
import setuptools


with open('requirements.txt') as f:
    requirements = f.read().splitlines()

if __name__ == "__main__":
    setuptools.setup(
        install_requires=requirements,
        use_scm_version = {
            # write_to needs be duplicated in pyproject.coml for compatibility
            # reasons
            "write_to": "divio_cli/version.py"
        }
    )
