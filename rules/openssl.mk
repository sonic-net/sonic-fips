# openssl

OPENSSL_VERSION_MAIN = 3.0.15
OPENSSL_VERSION_FULL = $(OPENSSL_VERSION_MAIN)-1~deb12u1
OPENSSL_VERSION_FIPS = $(OPENSSL_VERSION_FULL)+fips
OPENSSL = openssl_$(OPENSSL_VERSION_FIPS)_$(ARCH).deb
$(OPENSSL)_SRC_PATH = $(SRC_PATH)/openssl
OPENSSL_DST_PATH = openssl-$(OPENSSL_VERSION_MAIN)

# Download openssl code
$(OPENSSL)_PRE_SCRIPT = rm -rf $(OPENSSL_DST_PATH); \
						rm -rf $(SRC_PATH)/openssl; \
						dget -u http://deb.debian.org/debian/pool/main/o/openssl/openssl_$(OPENSSL_VERSION_FULL).dsc; \
						mv $(OPENSSL_DST_PATH) $(SRC_PATH)/openssl; \
						pushd $(SRC_PATH)/openssl; \
						quilt pop -a -f; \
						rm -rf .pc; \
						popd;

MAIN_TARGETS += $(OPENSSL)
$(OPENSSL)_DERIVED_DEBS = libssl3_$(OPENSSL_VERSION_FIPS)_$(ARCH).deb
$(OPENSSL)_DERIVED_DEBS += libssl-dev_$(OPENSSL_VERSION_FIPS)_$(ARCH).deb
$(OPENSSL)_DERIVED_DEBS += openssl-dbgsym_$(OPENSSL_VERSION_FIPS)_$(ARCH).deb
$(OPENSSL)_DERIVED_DEBS += libssl3-dbgsym_$(OPENSSL_VERSION_FIPS)_$(ARCH).deb
$(OPENSSL)_DERIVED_DEBS += libssl-doc_$(OPENSSL_VERSION_FIPS)_all.deb
