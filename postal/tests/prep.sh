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

# Install Vault
curl -o vault.zip https://releases.hashicorp.com/vault/0.11.5/vault_0.11.5_linux_amd64.zip ; yes | unzip vault.zip

if [ -f .env ] ; then mv .env .env.bak ; fi
