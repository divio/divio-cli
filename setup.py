#!/usr/bin/env python
# -*- coding: utf-8 -*-
from setuptools import setup, find_packages
from cmscloud_client import __version__


INSTALL_REQUIRES = [
    'requests',
    'docopt',
    'pyyaml',
]
try:
    import json
except ImportError:
    INSTALL_REQUIRES.append('simplejson')

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
    name='cmscloud-client',
    version=__version__,
    description='The command-line client for the django CMS cloud',
    author='The django CMS cloud team',
    author_email='info@divio.ch',
    url='http://django-cms.com/',
    packages=find_packages(),
    license='BSD',
    platforms=['OS Independent'],
    install_requires=INSTALL_REQUIRES,
    entry_points="""
    [console_scripts]
    cmscloud = cmscloud_client.cli:main
    """,
)
