# -*- coding: utf-8 -*-

import os
import platform

if platform.system() == 'Linux':
    try:
        import dbus
    except:
        pass

if 'HOME' not in os.environ:
    os.environ['HOME'] = os.path.expanduser("~")
from aldryn_client.main import AldrynGUIApp

if __name__ == '__main__':
    AldrynGUIApp().run()
