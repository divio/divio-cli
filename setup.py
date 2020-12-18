#!/usr/bin/env python
import sys

from setuptools import setup, find_packages

from setuptools_scm import get_version


with open('requirements.txt') as f:
    requirements = f.read().splitlines()

if sys.platform == 'win32':
    with open('requirements-windows.txt') as f:
        requirements += f.read().splitlines()


CLASSIFIERS = [
    'Development Status :: 4 - Beta',
    'Environment :: Console',
    'Intended Audience :: Developers',
    'License :: OSI Approved :: BSD License',
    'Operating System :: OS Independent',
    'Programming Language :: Python',
    'Programming Language :: Python :: 2',
    'Programming Language :: Python :: 2.7',
    'Programming Language :: Python :: 3',
    'Programming Language :: Python :: 3.5',
    'Programming Language :: Python :: 3.6',
    'Programming Language :: Python :: 3.7',
    'Programming Language :: Python :: 3.8',
    'Topic :: Software Development',
]

long_description = """
The Divio CLI is a tool for interacting with Divio projects and the Divio cloud infrastructure.

It provides commands to set up projects locally, push and pull media and database content to
remote cloud projects, get and set environment variables, and so on.

How to get started with the Divio CLI: https://docs.divio.com/en/latest/how-to/local-cli/

Divio CLI reference: https://docs.divio.com/en/latest/reference/divio-cli
"""

setup(
    name='divio-cli',
    version=get_version(),
    description='The command-line client for the Divio Cloud',
    long_description=long_description,
    author='Divio AG',
    author_email='info@divio.com',
    url='https://docs.divio.com/en/latest/how-to/local-cli/',
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    license='BSD',
    platforms=['OS Independent'],
    install_requires=requirements,
    extras_require={
        'crypto': [
            'cryptography',
        ],
    },
    entry_points="""
    [console_scripts]
    divio = divio_cli.cli:cli
    aldryn = divio_cli.cli:cli
    """,
    use_scm_version=True,
    setup_requires=['setuptools_scm'],
)
