#!/bin/bash

echo '***********************************'
echo 'AldrynCloud OS X deployment script'
echo '***********************************'
rm -f ./aldryn_client/aldryngui.ini
rm -rf ./dist/AldrynCloud
rm -rf ./dist/AldrynCloud.app
rm -rf ./dist/AldrynCloud.dmg
kivy ../PyInstaller-2.1/pyinstaller.py bin/AldrynCloud.spec
hdiutil create ./dist/AldrynCloud.dmg -srcfolder ./dist/AldrynCloud.app -ov
open ./dist
echo '***********************************'
echo 'App file: dist/AldrynCloud.app'
echo 'DMG file: dist/AldrynCloud.dmg'
echo '***********************************'
