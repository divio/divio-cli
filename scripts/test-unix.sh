#!/bin/bash
set -e

IMAGES='debian ubuntu fedora centos oraclelinux opensuse base/archlinux'

echo "==== pulling images ===="

for IMAGE in $IMAGES
do
	docker pull $IMAGE
done


for IMAGE in $IMAGES
do
	echo "==== testing $IMAGE ===="
	docker run --rm -it -v "$PWD/binary/divio-Linux:/bin/divio:ro" $IMAGE divio version
done
