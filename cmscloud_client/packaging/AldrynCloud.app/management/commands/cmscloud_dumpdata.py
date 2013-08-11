# -*- coding: utf-8 -*-
from cmscloud_client.serialize import Dumper
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.translation import get_language
import os


class Command(BaseCommand):
    def handle(self, outfile=None, language=None, **options):
         if outfile is None:
             print "You must specify a file to write to as first argument"
             return
         if language is None:
             print "You must specify a language code (eg: en) as second argument"
             return
         datadir = os.path.join(os.path.dirname(outfile), 'data')
         dumper = Dumper(datadir, language, getattr(settings, 'CMSCLOUD_DUMPDATA_FOLLOW', []))
         dumper.dump(outfile)


