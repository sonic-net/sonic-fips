#!/bin/sh
# Regenerate Debian's configure changes with the selected build tools.
set -eu
"$AUTOCONF" --include=config
"$AUTOHEADER" --include=config
export PATH="$KERBEROS_BUILD_TOOLS/bin:$PATH"
export CPP="$CC ${CFLAGS:-} -E"
# Some upstream test-program rules (notably t_trval) link with CC alone.
# Keep the declared startup objects and library paths on those invocations.
export CC="$CC $LDFLAGS"
pcdir="$PWD/.bazel-pkgconfig"
mkdir -p "$pcdir"
for metadata in $BAZEL_PKGCONFIG_FILES; do
    source="$EXT_BUILD_ROOT/$metadata"
    target="$pcdir/$(basename "$metadata")"
    if [ -e "$target" ]; then
        cmp "$source" "$target"
    else
        ln -s "$source" "$target"
    fi
done
export PKG_CONFIG_LIBDIR="$pcdir"
export PKG_CONFIG_PATH=
export PKG_CONFIG="$BAZEL_PKGCONF --define-variable=prefix=$EXT_BUILD_DEPS --define-variable=libdir=$EXT_BUILD_DEPS/lib --define-variable=includedir=$EXT_BUILD_DEPS/include/usr/include"
openssl_dir=
for candidate in "$EXT_BUILD_DEPS"/build/usr/lib/*/libcrypto.so.3; do
    test -f "$candidate" || continue
    test -z "$openssl_dir"
    openssl_dir=$(dirname "$candidate")
done
test -n "$openssl_dir"
./configure "$@"
printf '\nSONIC_OPENSSL_LIBDIR := %s\nSONIC_DEPENDENCY_LIBDIR := %s\n' "$openssl_dir" "$EXT_BUILD_DEPS/lib" >> Makefile
# Run the original crypto test directory after the ordinary build, without
# starting KDC/network services or changing the production build's test policy.
cat >> Makefile <<'MAKE'

# AUTO-GENERATED. DO NOT EDIT MANUALLY.
# Generator: krb5/configure.sh
.PHONY: sonic-crypto-tests
sonic-crypto-tests:
	$(MAKE) -C lib/crypto/crypto_tests check RUN_SETUP='LD_LIBRARY_PATH=$(CURDIR)/lib:$(SONIC_OPENSSL_LIBDIR):$(SONIC_DEPENDENCY_LIBDIR)'
	mkdir -p "$(DESTDIR)"
	LD_LIBRARY_PATH='$(CURDIR)/lib:$(SONIC_OPENSSL_LIBDIR):$(SONIC_DEPENDENCY_LIBDIR)' LD_DEBUG=libs ./lib/crypto/crypto_tests/t_encrypt > "$(DESTDIR)/crypto-loader.stdout" 2> "$(DESTDIR)/crypto-loader.log"
	grep 'calling init:' "$(DESTDIR)/crypto-loader.log" | grep -F '$(SONIC_OPENSSL_LIBDIR)/libcrypto.so.3'
	printf '%s\n' '{"_generated":{"notice":"AUTO-GENERATED. DO NOT EDIT MANUALLY.","generator":"krb5/configure.sh"},"status":"passed","target":"lib/crypto/crypto_tests check","source_openssl_load":"passed"}' > "$(DESTDIR)/crypto-tests.json"
MAKE
