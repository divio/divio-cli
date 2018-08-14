# stop on first error
$ErrorActionPreference = "Stop"

# create new venv
python -m pip install --upgrade pip
pip install virtualenv
virtualenv venv
.\venv\Scripts\activate

# pip and pyinstaller generate lots of warnings, so we need to ignore them
$ErrorActionPreference = "Continue"

# install build requirements
pip install  -r requirements.txt -r requirements-windows.txt -r requirements-build.txt
pip install cryptography

# install divio-cli
pip install -e .

# prepare out folder
md -Force binary

# package app
pyinstaller.exe -F -y scripts\entrypoint.py -n divio-Windows.exe --hidden-import=_cffi_backend --distpath=binary

$ErrorActionPreference = "Stop"

# run check against newly built binary
.\binary\divio-Windows version
