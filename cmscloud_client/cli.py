# -*- coding: utf-8 -*-
import docopt
import imp
import os
import sys

from cmscloud_client import __version__ as version
from cmscloud_client.client import Client
from cmscloud_client.utils import cli_confirm

try:
    imp.find_module('kivy')
except ImportError:
    GUI = False
else:
    GUI = True

doc_draft = """django CMS cloud client.

Usage:%(extra_commands)s
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

gui_command = """
    cmscloud gui"""

if GUI:
    __doc__ = doc_draft % {'extra_commands': gui_command}
else:
    __doc__ = doc_draft % {'extra_commands': ''}


def _network_error_callback(message, on_confirm, on_cancel):
    question = 'Retry syncing the file?'
    if cli_confirm(question, message=message, default=True):
        on_confirm()
    else:
        on_cancel()


def main():
    args = docopt.docopt(__doc__, version=version)
    client = Client(
        os.environ.get(Client.CMSCLOUD_HOST_KEY, Client.CMSCLOUD_HOST_DEFAULT),
        interactive=True)
    retval = True
    msg = None
    if GUI and args['gui']:
        from main import CMSCloudGUIApp
        CMSCloudGUIApp().run()
    elif args['login']:
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
        retval, msg = client.sync(
            args.get('--sitename', None),
            network_error_callback=_network_error_callback)
    elif args['sites']:
        retval, msg = client.sites()
    if msg:
        print msg
    sys.exit(int(retval))
