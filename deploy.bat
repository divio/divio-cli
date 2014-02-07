@echo off
echo ***********************************
echo AldrynCloud Win32 deployment script
echo ***********************************
del .\aldryn_client\aldryngui.ini
call pip install requests
python ..\PyInstaller-2.1\pyinstaller.py bin\AldrynCloud.spec
echo ***********************************
echo Binary file: dist\AldrynCloud.exe
echo ***********************************
