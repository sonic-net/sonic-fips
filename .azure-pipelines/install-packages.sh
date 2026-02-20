#!/bin/bash

set -x
sudo mkdir -p $HOME
sudo chown $USER $HOME
sudo apt-get update
sudo apt-get install -y git python3-pip
sudo apt-get install -y cmake git make build-essential quilt debhelper bc python3 python3-pip sudo libssl-dev libgcc-12-dev
sudo apt-get install -y clang
sudo apt-get install -y openssl libssl-dev libssl3
sudo apt-get install -y dh-exec dh-runit libaudit-dev libedit-dev libfido2-dev libgtk-3-dev libkrb5-dev
sudo apt-get install -y libwrap0-dev pkg-config
sudo apt-get install -y libpam-dev libselinux1-dev libsystemd-dev libwrap0-dev

# Install dget for download debian package source code
sudo apt-get install -y devscripts

# Build Golang
sudo apt-get install -y golang

# Build Python
sudo apt-get install -y lsb-release sharutils libreadline-dev libncursesw5-dev  libbz2-dev liblzma-dev libgdbm-dev libdb-dev tk-dev blt-dev  libexpat1-dev libbluetooth-dev locales-all libsqlite3-dev media-types
sudo apt-get install -y time net-tools xvfb systemtap-sdt-dev python3-sphinx python3-docs-theme texinfo

# Build krb5
sudo apt-get install -y ss-dev libldap2-dev libc6-dev libkeyutils-dev byacc docbook-to-man libsasl2-dev libverto-dev python3-cheetah python3-lxml doxygen doxygen-latex tex-gyre

sudo pip3 install --break-system-packages blurb

[ -f  src/SymCrypt/scripts/requirements.txt ] && sudo pip3 install -r src/SymCrypt/scripts/requirements.txt
if [ "$ARCH" == "armhf" ]; then
    sudo apt-get install -y libc6-dev-armhf-cross
    sudo ln -s /usr/include/arm-linux-gnueabihf/openssl/opensslconf.h /usr/include/openssl/opensslconf.h
fi
