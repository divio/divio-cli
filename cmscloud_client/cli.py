# -*- coding: utf-8 -*-
import sys
from cmscloud_client import __version__ as version
from cmscloud_client.client import Client
import docopt
import os

__doc__ = """django CMS cloud client.

Usage:
    cmscloud login
    cmscloud boilerplate upload
    cmscloud boilerplate validate
    cmscloud app upload
    cmscloud app validate
    cmscloud sync [--sitename=<sitename>]

Options:
    -h --help                   Show this screen.
    --version                   Show version.
    --sitename=<sitename>       Domain of your site, eg example.cloud.django-cms.com.
"""


def main():
    args = docopt.docopt(__doc__, version=version)
    client = Client(os.environ.get('CMSCLOUD_HOST', 'https://control.django-cms.com'))
    retval = True
    if args['login']:
        retval = client.login()
    elif args['boilerplate']:
        if args['upload']:
            retval = client.upload_boilerplate()
        elif args['validate']:
            retval = client.validate_boilerplate()
    elif args['app']:
        if args['upload']:
            retval = client.upload_app()
        elif args['validate']:
            retval = client.validate_app()
    elif args['sync']:
        retval = client.sync(args.get('--sitename', None))
    sys.exit(int(retval))
