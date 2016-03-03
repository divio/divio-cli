# stop on first error
$ErrorActionPreference = "Stop"

$ARCH = "Windows"
$VENV = "venv-" + $ARCH

# cleanup
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue dist
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue aldryn_client.egg-info
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $VENV

# create new venv
C:\Python27\Scripts\pip.exe install --upgrade pip
C:\Python27\Scripts\pip.exe install virtualenv
C:\Python27\Scripts\virtualenv.exe $VENV

# install build requirements
Invoke-Expression ".\$VENV\Scripts\pip.exe install -r requirements.txt -r requirements-windows.txt -r requirements-build.txt"

# install aldryn-client
Invoke-Expression ".\$VENV\Scripts\pip.exe install -e ."

# prepare out folder
md -Force binary

# package app
Invoke-Expression ".\$VENV\Scripts\pyinstaller.exe -F -y scripts\entrypoint.py -n aldryn-$ARCH.exe --distpath=binary"

# run check
Invoke-Expression ".\binary\aldryn-$ARCH version"
