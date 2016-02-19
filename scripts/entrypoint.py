#!..\venv\Scripts\python.exe
# -*- coding: utf-8 -*-

"""
This file is auto created on *nix platforms. On Windows it just creates
a binary exe instead which can't be read by PyInstaller.
"""

import re
import sys

from aldryn_client.cli import cli

if __name__ == '__main__':
    sys.argv[0] = re.sub(r'(-script\.pyw|\.exe)?$', '', sys.argv[0])
    sys.exit(cli())

