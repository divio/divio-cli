# -*- mode: python -*-  
from kivy.tools.packaging.pyinstaller_hooks import install_hooks
install_hooks(globals())

a = Analysis(['./bin/AldrynCloud.py'],
             hiddenimports=['cmscloud_client.management.commands', 'kivy.core.image.img_gif', 'kivy.core.image.img_pil', 'git']
             )

### http://www.pyinstaller.org/ticket/783
for d in a.datas:
    if 'pyconfig' in d[0]: 
        a.datas.remove(d)
        break

a.datas += Tree('./cmscloud_client/resources', './resources')
a.datas += Tree('./cmscloud_client/img', './img')
a.datas += [('./cacert.pem', './cmscloud_client/cacert.pem', 'DATA')]
a.datas += [('cmscloud_client/cmscloudgui.kv', './cmscloud_client/cmscloudgui.kv', 'DATA')]

pyz = PYZ(a.pure)
exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          name=os.path.join('dist', 'AldrynCloud.exe'),
          debug=False,
          strip=None,
          upx=True,
          console=False,
          icon="./cmscloud_client/resources/appIcon.ico")
