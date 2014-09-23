#!/bin/bash

echo '***********************************'
echo 'Aldryn Linux deployment script     '
echo '***********************************'
rm -rf ./build
mkdir -p ./build
mkdir -p ./dist
sudo python setup.py install
rm -f ./aldryn_client/aldryngui.ini
rm -rf ./dist/Aldryn
rm -rf ./dist/Aldryn.bin
python ../PyInstaller-2.1/pyinstaller.py bin/Aldryn.spec
open ./dist
echo '***********************************'
echo 'Bin file: dist/Aldryn.bin'
echo '***********************************'

