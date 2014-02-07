#!/bin/bash

## Remove previous builds.  Start with clean slate.
cd ../../packages/aldryn_client/
rm -rf build dist

cd ../../aldryn-client/aldryn_client/

## Force build with custom installed python
/Library/Frameworks/Python.framework/Versions/2.7/bin/python setup.py py2app --dist-dir=../../packages/aldryn_client/dist --bdist-base=../../packages/aldryn_client/build
