.ONESHELL:
SHELL = /bin/bash
.SHELLFLAGS += -e

ARCH ?= amd64
CMAKE_BUILD_TYPE ?= Release
BUILD_JOBS ?= $(shell nproc)
BUILD_NAME = symcrypt-openssl
SYMCRYPT_OPENSSL_VERSION ?= 0.1
SYMCRYPT_PACKAGE = $(BUILD_NAME)_$(SYMCRYPT_OPENSSL_VERSION)_$(ARCH).deb
BUILD_ROOT_DIR = tmp/$(BUILD_NAME)
SYMCRYPT_TEST ?= y

CMAKE_ARCH = AMD64
LIB_INSTALL_NAME = x86_64-linux-gnu
ifeq ($(ARCH), arm64)
CMAKE_ARCH = ARM64
LIB_INSTALL_NAME = aarch64-linux-gnu
CMAKE_C_FLAGS = -mno-outline-atomics
else ifeq ($(ARCH), armhf)
CMAKE_ARCH = ARM
LIB_INSTALL_NAME = arm-linux-gnueabihf
BUILD_JOBS = 1
endif

CMAKE_ARCH_LOWER = $(shell echo $(CMAKE_ARCH) | tr '[:upper:]' '[:lower:]')

INSTALL_PATH = $(BUILD_ROOT_DIR)/usr/lib/$(LIB_INSTALL_NAME)
ENGINES_PATH = $(INSTALL_PATH)/engines-3
PROVIDERS_PATH = $(INSTALL_PATH)/ossl-modules
DEBIAN_DIR = $(BUILD_ROOT_DIR)/DEBIAN

ROOT_PATH = $(shell realpath $(shell pwd)/../..)
DEST ?= $(ROOT_PATH)/target
LIBSYMCRYPT = $(DEST)/libsymcrypt.so
LIBSYMCRYPTENGINE = $(DEST)/libsymcryptengine.so
LIBSYMCRYPTPROVIDER = $(DEST)/symcryptprovider.so
TARGET = $(DEST)/$(SYMCRYPT_PACKAGE)

DEPENDS := $(LIBSYMCRYPT) $(LIBSYMCRYPTPROVIDER)

all: $(TARGET)

list:
	@$(foreach target,$(DEPENDS) $(TARGET),echo $(target);)

$(LIBSYMCRYPT):
	cd ../SymCrypt
	if [ "$(ARCH)" == armhf ]; then
	    python3 scripts/build.py cmake --arch $(CMAKE_ARCH_LOWER) --config $(CMAKE_BUILD_TYPE) --toolchain cmake-configs/Toolchain-GCC-ARM.cmake bin
	else
	    cmake -S . -B bin -DSYMCRYPT_TARGET_ARCH=$(CMAKE_ARCH) -DCMAKE_BUILD_TYPE=$(CMAKE_BUILD_TYPE) -DCMAKE_C_FLAGS=$(CMAKE_C_FLAGS) -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++
	    cmake --build bin -j$(BUILD_JOBS)
	fi
	if [ "$(SYMCRYPT_TEST)" == "y" ]; then bin/exe/symcryptunittest; fi
	mkdir -p $(DEST)/debug
	cp -a bin/module/generic/libsymcrypt.so* $(DEST)/
	cp -a bin/module/generic/processing/libsymcrypt.so* $(DEST)/debug/
	cp -r bin/exe $(DEST)/debug/

$(LIBSYMCRYPTPROVIDER): $(LIBSYMCRYPT)
	cd ../SymCrypt-OpenSSL
	cp -P $(DEST)/libsymcrypt.so* ./
	mkdir -p bin
	cd bin
	cmake .. -DCMAKE_TOOLCHAIN_FILE=../cmake-toolchain/LinuxUserMode-$(CMAKE_ARCH).cmake -DSYMCRYPT_ROOT_DIR=$(ROOT_PATH)/src/SymCrypt -DCMAKE_BUILD_TYPE=$(CMAKE_BUILD_TYPE)
	cmake --build .
	rm ../libsymcrypt.so*
	cp -a SymCryptProvider/symcryptprovider.so $(LIBSYMCRYPTPROVIDER)
	cp -a SymCryptEngine/dynamic/symcryptengine.so $(LIBSYMCRYPTENGINE)

$(TARGET): $(DEPENDS)
	mkdir -p $(INSTALL_PATH)
	mkdir -p $(PROVIDERS_PATH)
	mkdir -p $(DEBIAN_DIR)
	mkdir -p $(BUILD_ROOT_DIR)/etc/ssl
	mkdir -p $(ENGINES_PATH)
	cp -a $(DEST)/libsymcrypt.so* $(INSTALL_PATH)/
	cp $(LIBSYMCRYPTENGINE) $(INSTALL_PATH)/
	cp -a $(LIBSYMCRYPTPROVIDER) $(PROVIDERS_PATH)/
	ln -sf $(shell basename $(LIBSYMCRYPTENGINE)) $(INSTALL_PATH)/symcryptengine.so
	ln -sf ../$(shell basename $(LIBSYMCRYPTENGINE)) $(ENGINES_PATH)/symcryptengine.so
	cp -rf debian/* $(DEBIAN_DIR)/
	chmod a+r -R $(INSTALL_PATH)/
	fakeroot dpkg-deb --build $(BUILD_ROOT_DIR) $(TARGET)