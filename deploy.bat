@echo off
echo ***********************************
echo AldrynCloud Win32 deployment script
echo ***********************************
REM FIXME: Broken if uses 'pip install twisted'
easy_install twisted
pip install autobahn
pip install watchdog
pip install requests
python ..\PyInstaller-2.1\pyinstaller.py bin\AldrynCloud.spec
echo ***********************************
echo Binary file: dist\AldrynCloud.exe
echo ***********************************