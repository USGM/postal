#!/bin/bash

#
# Prepare build environment
#

set -x

mkdir -p $WORKSPACE/.local/bin

# Install docker-compose
curl -L https://github.com/docker/compose/releases/download/1.21.2/docker-compose-$(uname -s)-$(uname -m) \
    -o $WORKSPACE/.local/bin/docker-compose
chmod a+x $WORKSPACE/.local/bin/docker-compose

if [ -f .env ] ; then mv .env .env.bak ; fi
