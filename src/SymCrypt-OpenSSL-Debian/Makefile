.ONESHELL:
SHELL = /bin/bash
.SHELLFLAGS += -e

ARCH ?= amd64
BUILD_NAME = symcrypt-openssl
BUILD_VERSION = 0.1
SYMCRYPT_PACKAGE = $(BUILD_NAME)_$(BUILD_VERSION)_$(ARCH).deb
BUILD_ROOT_DIR = tmp/$(BUILD_NAME)

CMAKE_ARCH = AMD64
LIB_INSTALL_NAME = x86_64-linux-gnu
ifeq ($(ARCH), arm64)
CMAKE_ARCH = ARM64
LIB_INSTALL_NAME = aarch64-linux-gnu
else ifeq ($(ARCH), armhf)
CMAKE_ARCH = ARMHF
LIB_INSTALL_NAME = arm-linux-gnueabihf 
endif

# TODO: Support arm64 and armhf
INSTALL_PATH = $(BUILD_ROOT_DIR)/usr/lib/$(LIB_INSTALL_NAME)
DEBIAN_DIR = $(BUILD_ROOT_DIR)/DEBIAN

ROOT_PATH = $(shell realpath $(shell pwd)/../..)
TARGET_PATH = $(ROOT_PATH)/target
LIBSYMCRYPT = $(TARGET_PATH)/libsymcrypt.so
LIBSYMCRYPTENGINE = $(TARGET_PATH)/libsymcryptengine.so
TARGET = $(TARGET_PATH)/$(SYMCRYPT_PACKAGE)

DEPENDS := $(LIBSYMCRYPT) $(LIBSYMCRYPTENGINE)

all: $(TARGET)

$(LIBSYMCRYPT):
	cd ../SymCrypt
	mkdir -p bin
	cd bin
	cmake .. -DCMAKE_TOOLCHAIN_FILE=../cmake-toolchain/LinuxUserMode-$(CMAKE_ARCH).cmake
	cmake --build .
	mkdir -p $(TARGET_PATH)
	cp module/$(CMAKE_ARCH)/LinuxUserMode/generic_linux/libsymcrypt.so $(LIBSYMCRYPT)

$(LIBSYMCRYPTENGINE): $(LIBSYMCRYPT)
	cd ../SymCrypt-OpenSSL
	cp $(LIBSYMCRYPT) ./
	ln -sf $(ROOT_PATH)/src/SymCrypt ~/SymCrypt
	mkdir -p bin
	cd bin
	cmake .. -DCMAKE_TOOLCHAIN_FILE=../cmake-toolchain/LinuxUserMode-$(CMAKE_ARCH).cmake
	cmake --build .
	rm ../libsymcrypt.so
	cp SymCryptEngine/dynamic/libsymcryptengine.so $(LIBSYMCRYPTENGINE)

$(TARGET): $(DEPENDS)
	mkdir -p $(INSTALL_PATH)
	mkdir -p $(DEBIAN_DIR)
	mkdir -p $(BUILD_ROOT_DIR)/usr/lib/ssl
	cp $(LIBSYMCRYPT) $(INSTALL_PATH)
	cp $(LIBSYMCRYPTENGINE) $(INSTALL_PATH)
	chmod o+r $(INSTALL_PATH)/*
	cp -rf debian/* $(DEBIAN_DIR)/
	cp openssl.cnf $(BUILD_ROOT_DIR)/usr/lib/ssl/openssl-fips.cnf
	dpkg-deb --build $(BUILD_ROOT_DIR) $(TARGET)