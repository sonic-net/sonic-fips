.ONESHELL:
SHELL = /bin/bash
.SHELLFLAGS += -e

ROOT_PATH = $(shell realpath $(shell pwd)/../..)
DEST ?= $(ROOT_PATH)/target
MAIN_TARGET = $(DEST)/$(GOLANG)
DERIVED_TARGETS = $(GOLANG)_DERIVED_DEBS

include $(ROOT_PATH)/rules/golang.mk

all: $(MAIN_TARGET)

$(MAIN_TARGET):
	cd ../golang-fips
	scripts/full-initialize-repo.sh $(GOLANGT_TAG)
	cp -r ../golang-debian/debian go/
	sed -i '/^0006-cmd-compile-fix-mergelocals-for-arm32-s390x-riscv64.patch$/d' go/debian/patches/series
	cd go
	sed -i "s/$(GOLANG_VERSOIN)/$(GOLANG_VERSOIN)+fips/" debian/changelog
	cp ../../golang/patches/*.patch debian/patches/
	comm -23 --nocheck-order ../../golang/patches/series debian/patches/series >> debian/patches/series
	dpkg-buildpackage -b -d -rfakeroot -us -uc
	cp ../*.deb $(DEST)

$(addprefix $(DEST)/, $(TARGETS)) : $(DEST)/%: $(MAIN_TARGET)
