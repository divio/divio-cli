#!/bin/bash

# Setup
WORKSPACE_FOLDER="$HOME/deploy"
PYINSTALLER_FOLDER="$WORKSPACE_FOLDER/pyinstaller"
SEARCH_FOLDER="$WORKSPACE_FOLDER/cmscloud-client/cmscloud_client"
PACKAGING_FOLDER="$WORKSPACE_FOLDER/packages"
MAIN_PYTHON_SCRIPT="$WORKSPACE_FOLDER/cmscloud-client/cmscloud_client/main.py"
CONTENTS_FOLDER="$WORKSPACE_FOLDER/cmscloud-client/cmscloud_client/resources"
ICON_FILE="$CONTENTS_FOLDER/appIcon.icns"

# Config
DEPLOY_NAME="AldrynCloud"
DIST_FOLDER="$PYINSTALLER_FOLDER/$DEPLOY_NAME/dist"

# Cleaning up
rm -rf $PACKAGING_FOLDER/$DEPLOY_NAME.app
rm -rf $PACKAGING_FOLDER/$DEPLOY_NAME.dmg

# Building PyInstaller Settings
cd $PYINSTALLER_FOLDER
rm -rf $DEPLOY_NAME
python pyinstaller.py --windowed -n $DEPLOY_NAME $MAIN_PYTHON_SCRIPT
cd $DEPLOY_NAME
echo 'install_hooks(globals())' | cat - "$DEPLOY_NAME.spec" > temp && mv temp "$DEPLOY_NAME.spec"
echo 'from kivy.tools.packaging.pyinstaller_hooks import install_hooks' | cat - "$DEPLOY_NAME.spec" > temp && mv temp "$DEPLOY_NAME.spec"

#set hiddenimports
perl -i -pe 'BEGIN{undef $/;} s/hiddenimports=\[\],/hiddenimports=\['\"setuptools\"', '\"distutils\"', '\"cython\"', '\"requests\"', '\"watchdog\"', '\"certifi\"', '\"kivy.core.image.img_gif\"'],/smg' "$DEPLOY_NAME.spec"

#set hookspath to none, otherwise kivy breaks
perl -i -pe 'BEGIN{undef $/;} s/,\n\s+hookspath=None//smg' "$DEPLOY_NAME.spec"
perl -i -pe 'BEGIN{undef $/;} s/,\n\s+runtime_hooks=None//smg' "$DEPLOY_NAME.spec"

#Certifi
perl -ni -e 'print; print "import requests.utils\n" if $. ==7' "$DEPLOY_NAME.spec"
perl -ni -e 'print; print "a.datas.append((\"cacert.pem\", \"cacert.pem\", \"DATA\"))\n" if $. == 8' "$DEPLOY_NAME.spec"

#fix slashes in path of SEARCH_FOLDER
SEARCH_FOLDER=$(echo $SEARCH_FOLDER|sed "s/\\//\\\\\//g")
perl -i -pe 'BEGIN{undef $/;} s/COLLECT\(exe,/COLLECT\(exe, Tree\('\"$SEARCH_FOLDER\"'\),/smg' "$DEPLOY_NAME.spec"

#set application icon
ICON_FILE=$(echo $ICON_FILE|sed "s/\\//\\\\\//g")
perl -i -pe 'BEGIN{undef $/;} s/BUNDLE\(coll,/BUNDLE\(coll, icon='\"$ICON_FILE\"',/smg' "$DEPLOY_NAME.spec"

cd ..
rm -rf "./$DEPLOY_NAME/dist/$DEPLOY_NAME"
rm -rf "./$DEPLOY_NAME/dist/$DEPLOY_NAME.app"
kivy pyinstaller.py "./$DEPLOY_NAME/$DEPLOY_NAME.spec"

#Create DMG
pushd $DIST_FOLDER
hdiutil create ./$DEPLOY_NAME.dmg -srcfolder $DEPLOY_NAME.app -ov
popd

#Move created files to packaging folder
mv -f $DIST_FOLDER/$DEPLOY_NAME.app $PACKAGING_FOLDER/
mv -f $DIST_FOLDER/$DEPLOY_NAME.dmg $PACKAGING_FOLDER/

cd $PYINSTALLER_FOLDER
rm -rf $DEPLOY_NAME

#cd $PACKAGING_FOLDER
#cd ..
#open $PACKAGING_FOLDER
