#!/usr/bin/env python
from setuptools import setup, find_packages

from aldryn_client import __version__
from aldryn_client.utils import is_windows


INSTALL_REQUIRES = [
    'click',
    'requests',
    'tabulate',
]

if is_windows():
    INSTALL_REQUIRES += [
        'pyyaml',  # converting docker-compose configs
        'colorama',  # colored output
    ]

CLASSIFIERS = [
    'Development Status :: 5 - Production/Stable',
    'Environment :: Console',
    'Framework :: Django',
    'Intended Audience :: Developers',
    'License :: OSI Approved :: BSD License',
    'Operating System :: OS Independent',
    'Programming Language :: Python',
    'Programming Language :: Python :: 2.6',
    'Programming Language :: Python :: 2.7',
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
