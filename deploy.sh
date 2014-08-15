#!/bin/bash

echo '***********************************'
echo 'Aldryn OS X deployment script'
echo '***********************************'
rm -f ./aldryn_client/aldryngui.ini
rm -rf ./dist/Aldryn
rm -rf ./dist/Aldryn.app
rm -rf ./dist/Aldryn.dmg
kivy ../PyInstaller-2.1/pyinstaller.py bin/Aldryn.spec
open ./dist
echo '***********************************'
echo 'App file: dist/Aldryn.app'
echo 'DMG file: dist/Aldryn.dmg'
echo '***********************************'
