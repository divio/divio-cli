# -*- coding: utf-8 -*-
from optparse import make_option
from cmscloud_client.serialize import Dumper
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.translation import get_language
import os


class Command(BaseCommand):
    option_list = list(BaseCommand.option_list) + [
        make_option('-l', '--language'),
    ]

    def handle(self, outfile=None, **options):
         if outfile is None:
             print "You must specify a file to write to as first argument"
             return
         datadir = os.path.join(os.path.dirname(outfile), 'data')
         language = options.get('language') or get_language()
         dumper = Dumper(datadir, language, getattr(settings, 'CMSCLOUD_DUMPDATA_FOLLOW', []))
         dumper.dump(outfile)


