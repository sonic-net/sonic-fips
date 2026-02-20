#!/bin/bash

set -ex

export ARCH=armhf

# Install packages
sudo mkdir -p $HOME

# Make SymCrypt and OpenSSL
#sed -i 's/aarch32|armv8l/aarch32|armv7l|armv8l/' src/SymCrypt/cmake-configs/SymCrypt-Platforms.cmake
#sed -i 's/aarch32|armv8l/aarch32|armv7l|armv8l/' src/SymCrypt/scripts/build.py
#make symcrypt
#rm -f src/openssl/test/recipes/30-test_afalg.t
#make openssl

# Install SymCrypt and OpenSSL
sudo dpkg -i target/libssl*.deb target/openssl*.deb
sudo dpkg -i target/symcrypt-openssl*.deb

# Enable SymCrypt
sudo mkdir -p /etc/fips
echo 1 | sudo tee /etc/fips/fips_enable
openssl engine -v | grep -i symcrypt

# Build the OpenSSL again with SymCrypt enabled
rm -f src/openssl/test/recipes/30-test_afalg.t
echo 40-Modify-tests-with-unsupported-behavior.patch >> src/openssl.patch/series
if TARGET_PATH=target-test make openssl; then
  echo "OpenSSL tests succeeded"
else
  cat src/openssl.patch/skipped-openssl-tests.conf
  TESTS=$(cat src/openssl.patch/skipped-openssl-tests.conf | sed 's/^/-/' | xargs)
  pushd src/openssl/build_shared
  make TESTS="$TESTS" test
  popd
  echo 0 | sudo tee /etc/fips/fips_enable
fi
