# -*- coding: utf-8 -*-

import os
if 'HOME' not in os.environ:
    os.environ['HOME'] = os.path.expanduser("~")
from cmscloud_client.main import CMSCloudGUIApp

if __name__ == '__main__':
    CMSCloudGUIApp().run()
