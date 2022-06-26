# openssl

OPENSSL_VERSION = 1.1.1k-1+deb11u1
OPENSSL_VERSION_FIPS = $(OPENSSL_VERSION)+fips
OPENSSL = openssl_$(OPENSSL_VERSION_FIPS)_$(ARCH).deb
$(OPENSSL)_SRC_PATH = $(SRC_PATH)/openssl
$(OPENSSL)_BUILD_OPTIONS = LDLIBS="-lsymcryptengine"

MAIN_TARGETS += $(OPENSSL)
$(OPENSSL)_DERIVED_DEBS = libssl1.1_$(OPENSSL_VERSION_FIPS)_$(ARCH).deb
$(OPENSSL)_DERIVED_DEBS += libssl-dev_$(OPENSSL_VERSION_FIPS)_$(ARCH).deb
$(OPENSSL)_DERIVED_DEBS += openssl-dbgsym_$(OPENSSL_VERSION_FIPS)_$(ARCH).deb
$(OPENSSL)_DERIVED_DEBS += libssl1.1-dbgsym_$(OPENSSL_VERSION_FIPS)_$(ARCH).deb
$(OPENSSL)_DERIVED_DEBS += libssl-doc_$(OPENSSL_VERSION_FIPS)_all.deb
