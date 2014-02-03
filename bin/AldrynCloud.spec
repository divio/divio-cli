# -*- mode: python -*-
import platform
from kivy.tools.packaging.pyinstaller_hooks import install_hooks
install_hooks(globals())

# for __version__
execfile('./cmscloud_client/__init__.py')

system = platform.system()
if system == 'Windows':
    script = './bin/AldrynCloud.py'
else:
    script = './cmscloud_client/main.py'

a = Analysis([script],
             hiddenimports=['cmscloud_client.management.commands', 'kivy.core.image.img_gif', 'kivy.core.image.img_pil', 'git']
            )

a.datas += Tree('./cmscloud_client/resources', './resources')
a.datas += Tree('./cmscloud_client/img', './img')
a.datas += [('./cacert.pem', './cmscloud_client/cacert.pem', 'DATA')]

pyz = PYZ(a.pure)

if system == 'Windows':
    a.datas += [('cmscloud_client/cmscloudgui.kv', './cmscloud_client/cmscloudgui.kv', 'DATA')]

    ### http://www.pyinstaller.org/ticket/783
    for d in a.datas:
            if 'pyconfig' in d[0]:
                    a.datas.remove(d)
                    break

    from string import Template
    version_str = __version__ + '.0'
    version = tuple([int(i) for i in version_str.split('.')])

    with open('./bin/version_template.txt') as f:
            s = Template(f.read())
    s = s.substitute(version=version, version_str=version_str)
    with open('./build/version_info.txt', 'w') as f:
            f.write(s)

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
              icon="./cmscloud_client/resources/appIcon.ico",
              version='./build/version_info.txt')

elif system == 'Darwin':
    a.datas += [('./cmscloudgui.kv', './cmscloud_client/cmscloudgui.kv', 'DATA')]
    exe = EXE(pyz,
              a.scripts,
              exclude_binaries=1,
              name=os.path.join('build/pyi.darwin/AldrynCloud', 'AldrynCloud'),
              debug=False,
              strip=None,
              upx=True,
              console=True)

    coll = COLLECT(exe,
                   a.binaries,
                   a.zipfiles,
                   a.datas,
                   strip=None,
                   upx=True,
                   name=os.path.join('dist', 'AldrynCloud'))

    app = BUNDLE(coll,
                 icon="./cmscloud_client/resources/appIcon.icns",
                 name=os.path.join('dist', 'AldrynCloud.app'),
                 version=__version__)
else:
    print("TODO: %s" % (system))
