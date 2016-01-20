#!/usr/bin/env python
import sys

from setuptools import setup, find_packages

from aldryn_client import __version__


INSTALL_REQUIRES = [
    'click',
    'requests',
    'tabulate',
    'six',
]

if sys.platform == 'win32':
    INSTALL_REQUIRES += [
        'pyyaml',  # converting docker-compose configs
        'colorama',  # colored output
    ]

CLASSIFIERS = [
    'Development Status :: 4 - Beta',
    'Environment :: Console',
    'Intended Audience :: Developers',
    'License :: OSI Approved :: BSD License',
    'Operating System :: OS Independent',
    'Programming Language :: Python',
    'Programming Language :: Python :: 2',
    'Programming Language :: Python :: 2.6',
    'Programming Language :: Python :: 2.7',
    'Programming Language :: Python :: 3',
    'Programming Language :: Python :: 3.5',
    'Topic :: Software Development',
]

setup(
    name='aldryn-client',
    version=__version__,
    description='The command-line client for the Aldryn Cloud',
    author='Divio AG',
    author_email='aldryn@divio.ch',
    url='http://www.aldryn.com/',
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    license='BSD',
    platforms=['OS Independent'],
    install_requires=INSTALL_REQUIRES,
    entry_points="""
    [console_scripts]
    aldryn = aldryn_client.cli:cli
    """,
)
