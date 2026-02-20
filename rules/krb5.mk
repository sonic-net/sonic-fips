# krb5

KRB5_VERSION_MAIN = 1.20.1
KRB5_VERSION_FULL = $(KRB5_VERSION_MAIN)-2+deb12u2
KRB5_VERSION_FIPS = $(KRB5_VERSION_FULL)+fips
KRB5 = libk5crypto3_$(KRB5_VERSION_FIPS)_$(ARCH).deb
$(KRB5)_SRC_PATH = $(SRC_PATH)/krb5
KERB5_DST_PATH = krb5-$(KRB5_VERSION_MAIN)

# Download krb5 code
$(KRB5)_PRE_SCRIPT = rm -rf $(KERB5_DST_PATH); \
					 rm -rf $(SRC_PATH)/krb5; \
					 dget -u http://deb.debian.org/debian/pool/main/k/krb5/krb5_$(KRB5_VERSION_FULL).dsc; \
					 mv $(KERB5_DST_PATH) $(SRC_PATH)/krb5; \
					 pushd $(SRC_PATH)/krb5; \
					 quilt pop -a -f; \
					 rm -rf .pc; \
					 popd;

MAIN_TARGETS += $(KRB5)
$(KRB5)_DERIVED_DEBS =