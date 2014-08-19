#!/bin/bash

echo '***********************************'
echo 'Aldryn Linux deployment script     '
echo '***********************************'
python setup.py install
rm -rf ./build
rm -f ./aldryn_client/aldryngui.ini
rm -rf ./dist/Aldryn
rm -rf ./dist/Aldryn.bin
python ../PyInstaller-2.1/pyinstaller.py bin/Aldryn.spec
open ./dist
echo '***********************************'
echo 'Bin file: dist/Aldryn.bin'
echo '***********************************'

