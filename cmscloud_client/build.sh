#!/bin/bash

## Remove previous builds.  Start with clean slate.
cd ../../packages/cmscloud_client/
rm -rf build dist

cd ../../cmscloud-client/cmscloud_client/

## Force build with custom installed python
/Library/Frameworks/Python.framework/Versions/2.7/bin/python setup.py py2app --dist-dir=../../packages/cmscloud_client/dist --bdist-base=../../packages/cmscloud_client/build