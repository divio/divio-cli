# -*- mode: python -*-
import platform
from kivy.tools.packaging.pyinstaller_hooks import install_hooks
install_hooks(globals())

# for __version__
execfile('./aldryn_client/__init__.py')

system = platform.system()

a = Analysis(['./bin/Aldryn.py'],
             hiddenimports=['aldryn_client.management.commands', 'kivy.core.image.img_gif', 'kivy.core.image.img_pil', 'git', 'plyer.platforms.macosx.notification', 'plyer.platforms.linux.notification']
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
              name=os.path.join('dist', 'Aldryn.exe'),
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
              name=os.path.join('build/pyi.darwin/Aldryn', 'Aldryn'),
              debug=False,
              strip=None,
              upx=True,
              append_pkg=False,  # Must be False for codesign
              console=True)

    coll = COLLECT(exe,
                   a.binaries,
                   a.zipfiles,
                   a.datas,
                   strip=None,
                   upx=True,
                   name=os.path.join('dist', 'Aldryn'))

    app = BUNDLE(coll,
                 icon="./aldryn_client/resources/appIcon.icns",
                 name=os.path.join('dist', 'Aldryn.app'),
                 version=__version__)

    # Create DMG with Background and Applications folder
    import os
    import sys
    import shutil
    import shlex
    import re
    import time
    from subprocess import Popen, PIPE

    vol_name = "Aldryn"
    dist_dir = './dist'
    dmg_dir = 'dmg_dir'
    try:
        os.makedirs(os.path.join(dist_dir, dmg_dir))
        os.makedirs(os.path.join(dist_dir, dmg_dir, '.background'))
        shutil.copy('./bin/aldryndmg.png', os.path.join(dist_dir, dmg_dir, '.background'))
        # Add additional property list require for Notification API
        with open('./dist/%s.app/Contents/Info.plist' % vol_name, 'rb') as f:
            info_plist = f.read()
        info_plist = info_plist.replace("</dict>\n</plist>",
                                        "<key>CFBundleIdentifier</key>\n"
                                        "<string>com.divio.aldryn</string>\n"
                                        "<key>CFBundleSignature</key>\n"
                                        "<string>????</string>\n"
                                        "</dict>\n</plist>")
        with open('./dist/%s.app/Contents/Info.plist' % vol_name, 'wb') as f:
            f.write(info_plist)
        # Code signing by Developer ID Application certificate
        # for distributing applications outside the Mac App Store
        Popen(shlex.split('codesign -f -s "Divio AG" Aldryn.app'), cwd=dist_dir, stdout=PIPE).communicate()
        shutil.move('./dist/%s.app' % vol_name, os.path.join(dist_dir, dmg_dir))
    except:
        pass

    print("* Try unmounting existing disk image")
    umount_cmd = 'hdiutil detach /Volumes/%s' % vol_name
    Popen(shlex.split(umount_cmd), cwd=dist_dir,
            stdout=PIPE).communicate()

    print("* Creating intermediate DMG disk image: temp.dmg")
    print("  checking how much space is needed for disk image...")
    du_cmd = 'du -sh %s' % dmg_dir
    du_out = Popen(shlex.split(du_cmd), cwd=dist_dir, stdout=PIPE).communicate()[0]
    size, unit = re.search('(\d+)(.*?)\s+', du_out).group(1, 2)
    print("  build needs at least %s%s." % (size, unit))

    size = int(size) + 4
    print("* Allocating %d%s for temp.dmg" % (size, unit, ))
    create_dmg_cmd = 'hdiutil create -srcfolder %s -volname %s \
         -format UDRW -size %d%s temp.dmg' % (dmg_dir, vol_name, size, unit)
    Popen(shlex.split(create_dmg_cmd), cwd=dist_dir).communicate()

    print("*mounting intermediate disk image:")
    mount_cmd = 'hdiutil attach -readwrite -noverify -noautoopen "temp.dmg"'
    Popen(shlex.split(mount_cmd), cwd=dist_dir,
      stdout=PIPE).communicate()

    print("* Running Apple Script to configure DMG layout properties:")
    dmg_config_script = """
tell application "Finder"
    tell disk "%s"
        open
        set current view of container window to icon view
        set toolbar visible of container window to false
        set statusbar visible of container window to false
        set the bounds of container window to {270,100,902,582}
        set theViewOptions to the icon view options of container window
        set arrangement of theViewOptions to not arranged
        set icon size of theViewOptions to 72
        set background picture of theViewOptions to file ".background:aldryndmg.png"
        do shell script "ln -s /Applications /Volumes/Aldryn"
        close
        open
        delay 1
        set position of item "Aldryn" of container window to {160, 315}
        set position of item "Applications" of container window to {485, 315}
        set position of item ".background" of container window to {900, 900}
        set position of item ".DS_Store" of container window to {900, 900}
        set position of item ".fseventsd" of container window to {900, 900}
        set position of item ".Trashes" of container window to {900, 900}
        close
        open
        update without registering applications
        delay 5
        close
        eject
    end tell
end tell
    """ % vol_name
    print(Popen(['osascript'], cwd=dist_dir, stdin=PIPE,
        stdout=PIPE).communicate(dmg_config_script)[0])

    print("* Creating final disk image")
    convert_cmd = 'hdiutil convert "temp.dmg" -format UDZO -imagekey ' + \
      'zlib-level=9 -o %s' % (vol_name + '.dmg',)
    Popen(shlex.split(convert_cmd), cwd=dist_dir,
      stdout=PIPE).communicate()

    print("* Cleaning temporary files")
    try:
        os.remove('./dist/temp.dmg')
    except OSError:
        pass
    shutil.rmtree(os.path.join(dist_dir, dmg_dir), ignore_errors=True)

elif system == 'Linux':
    exe = EXE(pyz,
          a.scripts,
          a.binaries,
          a.zipfiles,
          a.datas,
          name=os.path.join('dist', 'Aldryn-%s.bin' % platform.architecture()[0]),
          debug=False,
          strip=None,
          upx=False,
          console=False)
else:
    print("TODO: %s" % (system))
