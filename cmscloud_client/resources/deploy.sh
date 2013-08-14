#!/bin/bash

WORKSPACE_FOLDER="/Users/christianbertschy/Documents/workspace"
PYINSTALLER_FOLDER="$WORKSPACE_FOLDER/pyinstaller"
SEARCH_FOLDER="$WORKSPACE_FOLDER/cmscloud-client/cmscloud_client"
PACKAGING_FOLDER="$WORKSPACE_FOLDER/cmscloud-client/cmscloud_client/packaging"
MAIN_PYTHON_SCRIPT="$WORKSPACE_FOLDER/cmscloud-client/cmscloud_client/main.py"
CONTENTS_FOLDER="$WORKSPACE_FOLDER/cmscloud-client/cmscloud_client/resources"

DEPLOY_NAME="AldrynCloud"
DIST_FOLDER="$PYINSTALLER_FOLDER/$DEPLOY_NAME/dist"

rm -rf $PACKAGING_FOLDER/$DEPLOY_NAME.app
rm -rf $PACKAGING_FOLDER/$DEPLOY_NAME.dmg

cd $PYINSTALLER_FOLDER
rm -rf $DEPLOY_NAME
python pyinstaller.py --name $DEPLOY_NAME $MAIN_PYTHON_SCRIPT
cd $DEPLOY_NAME
echo 'install_hooks(globals())' | cat - "$DEPLOY_NAME.spec" > temp && mv temp "$DEPLOY_NAME.spec"
echo 'from kivy.tools.packaging.pyinstaller_hooks import install_hooks' | cat - "$DEPLOY_NAME.spec" > temp && mv temp "$DEPLOY_NAME.spec"

#set hiddenimports
perl -i -pe 'BEGIN{undef $/;} s/hiddenimports=\[\],/hiddenimports=\['\"certifi\"'], hookspath=None,/smg' "$DEPLOY_NAME.spec"

#set hookspath to none, otherwise kivy breaks
perl -i -pe 'BEGIN{undef $/;} s/,\n\s+hookspath=None//smg' "$DEPLOY_NAME.spec"

#Certifi
perl -ni -e 'print; print "import requests.utils\n" if $. ==7' "$DEPLOY_NAME.spec"
perl -ni -e 'print; print "a.datas.append((\"cacert.pem\", \"cacert.pem\", \"DATA\"))\n" if $. == 8' "$DEPLOY_NAME.spec"

#fix slashes in path of SEARCH_FOLDER
SEARCH_FOLDER=$(echo $SEARCH_FOLDER|sed "s/\\//\\\\\//g")
perl -i -pe 'BEGIN{undef $/;} s/COLLECT\(exe,/COLLECT\(exe, Tree\('\"$SEARCH_FOLDER\"'\),/smg' "$DEPLOY_NAME.spec"

cd ..
rm -rf "./$DEPLOY_NAME/dist/$DEPLOY_NAME"
python pyinstaller.py "./$DEPLOY_NAME/$DEPLOY_NAME.spec"

cd $DIST_FOLDER
mv "$DEPLOY_NAME" "$DEPLOY_NAME.app"

#Add plist and icon manually, not yet supported by pyinstaller automatically
cd $CONTENTS_FOLDER
cp "appIcon.icns" "$DIST_FOLDER/$DEPLOY_NAME.app/"
cp "info.plist" "$DIST_FOLDER/$DEPLOY_NAME.app/"

#Create DMG
pushd $DIST_FOLDER
hdiutil create ./$DEPLOY_NAME.dmg -srcfolder $DEPLOY_NAME.app -ov
popd 

#Move created files to packaging folder
mv -f $DIST_FOLDER/$DEPLOY_NAME.app $PACKAGING_FOLDER/
mv -f $DIST_FOLDER/$DEPLOY_NAME.dmg $PACKAGING_FOLDER/

cd $PYINSTALLER_FOLDER
rm -rf $DEPLOY_NAME

cd $PACKAGING_FOLDER
cd ..
open $PACKAGING_FOLDER
 
