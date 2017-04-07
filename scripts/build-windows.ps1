# stop on first error
$ErrorActionPreference = "Stop"

$ARCH = "Windows"
$VENV = "venv-" + $ARCH

# cleanup
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue dist
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue divio_cli.egg-info
Remove-Item -Recurse -Force -ErrorAction SilentlyContinue $VENV

# create new venv
C:\Python27\Scripts\pip.exe install --upgrade pip
C:\Python27\Scripts\pip.exe install virtualenv
C:\Python27\Scripts\virtualenv.exe $VENV

# pip and pyinstaller generate lots of warnings, so we need to ignore them
$ErrorActionPreference = "Continue"

# install build requirements
Invoke-Expression ".\$VENV\Scripts\pip.exe install --allow-external pyinstaller -r requirements.txt -r requirements-windows.txt -r requirements-build.txt"
Invoke-Expression ".\$VENV\Scripts\pip.exe install cryptography"

# install divio-cli
Invoke-Expression ".\$VENV\Scripts\pip.exe install -e ."

# prepare out folder
md -Force binary

# package app
Invoke-Expression ".\$VENV\Scripts\pyinstaller.exe -F -y scripts\entrypoint.py -n divio-$ARCH.exe --hidden-import=_cffi_backend --distpath=binary"

$ErrorActionPreference = "Stop"

# run check
Invoke-Expression ".\binary\divio-$ARCH version"
