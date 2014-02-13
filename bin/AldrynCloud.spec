# -*- mode: python -*-
import platform
from kivy.tools.packaging.pyinstaller_hooks import install_hooks
install_hooks(globals())

# for __version__
execfile('./aldryn_client/__init__.py')

system = platform.system()

a = Analysis(['./bin/AldrynCloud.py'],
             hiddenimports=['aldryn_client.management.commands', 'kivy.core.image.img_gif', 'kivy.core.image.img_pil', 'git']
            )

a.datas += Tree('./aldryn_client/resources', './resources')
a.datas += Tree('./aldryn_client/img', './img')
a.datas += [('./cacert.pem', './aldryn_client/cacert.pem', 'DATA')]
a.datas += [('aldryn_client/aldryngui.kv', './aldryn_client/aldryngui.kv', 'DATA')]

pyz = PYZ(a.pure)

if system == 'Windows':
    a.datas += [('aldryn_client/aldryngui.kv', './aldryn_client/aldryngui.kv', 'DATA')]

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
              icon="./aldryn_client/resources/appIcon.ico",
              version='./build/version_info.txt')

elif system == 'Darwin':
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
                 icon="./aldryn_client/resources/appIcon.icns",
                 name=os.path.join('dist', 'AldrynCloud.app'),
                 version=__version__)
else:
    print("TODO: %s" % (system))
