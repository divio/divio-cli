# -*- coding: utf-8 -*-ALDRYN_DUMPDATA_FOLLOW
import os
from django.core.management.base import NoArgsCommand
from aldryn_client.serialize import Loader


class Command(NoArgsCommand):
    def handle(self, infile=None, language=None, **options):
        if infile is None:
            print "You must specify a file to read from as first argument"
            return
        if language is None:
            print "You must specify a language as second argument"
            return
        loader = Loader(language)
        loader.load(infile)
