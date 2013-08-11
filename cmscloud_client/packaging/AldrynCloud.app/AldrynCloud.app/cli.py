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
    cmscloud sites

Options:
    -h --help                   Show this screen.
    --version                   Show version.
    --sitename=<sitename>       Domain of your site, eg example.cloud.django-cms.com.
"""


def main():
    args = docopt.docopt(__doc__, version=version)
    client = Client(os.environ.get(Client.CMSCLOUD_HOST_KEY, Client.CMSCLOUD_HOST_DEFAULT))
    retval = True
    msg = None
    if args['login']:
        retval, msg = client.login()
    elif args['boilerplate']:
        if args['upload']:
            retval, msg = client.upload_boilerplate()
        elif args['validate']:
            retval, msg = client.validate_boilerplate()
    elif args['app']:
        if args['upload']:
            retval, msg = client.upload_app()
        elif args['validate']:
            retval, msg = client.validate_app()
    elif args['sync']:
        retval, msg = client.sync(args.get('--sitename', None))
    elif args['sites']:
        retval, msg = client.sites()
    if msg:
        print msg
    sys.exit(int(retval))
