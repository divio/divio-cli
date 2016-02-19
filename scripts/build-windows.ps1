$ErrorActionPreference = "Stop"

# Remove virtualenv
if (Test-Path venv) {
    Remove-Item -Recurse -Force .\venv
}

# Remove .pyc files
Get-ChildItem -Recurse -Include *.pyc | foreach ($_) { Remove-Item $_.FullName }

# Create virtualenv
virtualenv .\venv

# pip and pyinstaller generate lots of warnings, so we need to ignore them
$ErrorActionPreference = "Continue"

# Install dependencies
.\venv\Scripts\pip install pypiwin32==219
.\venv\Scripts\pip install -r requirements-windows.txt
.\venv\Scripts\pip install --no-deps .
.\venv\Scripts\pip install --allow-external pyinstaller -r requirements-build.txt

git rev-parse --short HEAD | out-file -encoding ASCII compose\GITSHA

# Build binary
.\venv\Scripts\pyinstaller .\aldryn.spec
$ErrorActionPreference = "Stop"

Move-Item -Force .\dist\aldryn.exe .\dist\aldryn-Windows-x86_64.exe
.\dist\aldryn-Windows-x86_64.exe version
