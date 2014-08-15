@echo off
echo ***********************************
echo Aldryn Win32 deployment script
echo ***********************************
del .\aldryn_client\aldryngui.ini
call pip install requests
python ..\PyInstaller-2.1\pyinstaller.py bin\Aldryn.spec
echo ***********************************
echo Binary file: dist\Aldryn.exe
echo ***********************************
