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
	cd go
	VERSION=$$(dpkg-parsechangelog --show-field Version) && \
	sed -i "s/$$VERSION/$${VERSION}+fips/" debian/changelog
	cp ../../golang/patches/*.patch debian/patches/
	comm -23 --nocheck-order ../../golang/patches/series debian/patches/series >> debian/patches/series
	dpkg-buildpackage -b -d -rfakeroot -us -uc
	# Verify sonic-fips patches were applied to the built package
	VERIFY_DIR=$$(mktemp -d)
	dpkg-deb -x ../golang-$(GOLANG_MAIN_VERSION)-go_*+fips*.deb $$VERIFY_DIR
	grep -q "sonic_fips" $$VERIFY_DIR/usr/share/go-*/src/crypto/internal/backend/hostfips.go \
		|| { echo "ERROR: sonic_fips patch not applied to Go package"; rm -rf $$VERIFY_DIR; exit 1; }
	grep -q "symcryptprovider" $$VERIFY_DIR/usr/share/go-*/src/vendor/github.com/golang-fips/openssl/v2/openssl.go \
		|| { echo "ERROR: symcryptprovider patch not applied to Go package"; rm -rf $$VERIFY_DIR; exit 1; }
	echo "Go FIPS patch verification passed"
	rm -rf $$VERIFY_DIR
	cp ../*.deb $(DEST)

$(addprefix $(DEST)/, $(TARGETS)) : $(DEST)/%: $(MAIN_TARGET)

