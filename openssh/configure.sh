#!/bin/sh
# Regenerate Debian's configure changes with declared build tools.
set -eu
# Large dependency include lists can overflow GCC's COLLECT_GCC_OPTIONS when
# it starts cc1. Ordinary @ expansion at the driver recreates that environment
# string; pass preprocessing options directly to cc1 with its response file.
cppflags_file="$PWD/.bazel-cppflags.rsp"
printf '%s\n' "${CPPFLAGS:-}" > "$cppflags_file"
if ! $CC ${CFLAGS:-} "-Wp,@$cppflags_file" -x c -fsyntax-only /dev/null; then
    echo "OpenSSH CPPFLAGS must contain GCC preprocessor options; use CFLAGS/LDFLAGS for driver options" >&2
    exit 1
fi
export CPPFLAGS="-Wp,@$cppflags_file"
# Force regeneration: a prior invocation may have patched the cached output.
"$AUTOCONF" --force
"$AUTOHEADER"
mkdir -p .pkgconfig-empty
export PKG_CONFIG_LIBDIR="$PWD/.pkgconfig-empty"
export PKG_CONFIG_PATH=
# Autoconf runs target conftest ELFs. Use the matching declared loader and
# source-built OpenSSL before Debian dependencies, without exporting target
# libc into host shell/coreutils processes or weakening feature probes.
SONIC_PROBE_RUNTIME=${AUTOCONF%/bin/autoconf}
SONIC_PROBE_LOADER=$(find "$SONIC_PROBE_RUNTIME/usr/lib" -name 'ld-linux-*.so.*' -print | head -n 1)
test -n "$SONIC_PROBE_LOADER"
SONIC_PROBE_LIBS="$EXT_BUILD_DEPS/build/usr/lib/x86_64-linux-gnu:$EXT_BUILD_DEPS/build/usr/lib/aarch64-linux-gnu:$EXT_BUILD_DEPS/lib:$SONIC_PROBE_RUNTIME/usr/lib/x86_64-linux-gnu:$SONIC_PROBE_RUNTIME/usr/lib/aarch64-linux-gnu"
export SONIC_PROBE_LOADER SONIC_PROBE_LIBS
# The generated Autoconf runner has two literal ac_try executable sites.
test "$(grep -c "ac_try='./conftest" configure)" = 2
sed -i "s|ac_try='./conftest|ac_try='\"\$SONIC_PROBE_LOADER\" --library-path \"\$SONIC_PROBE_LIBS\" ./conftest|g" configure
# Autoconf's preprocessor probes omit CFLAGS. Keep the declared compiler's
# system-header flags instead of falling back to the runner's /lib/cpp.
export CPP="$CC ${CFLAGS:-} -E"
# Debian's extra version identifies the same source/patch set as the Make build.
./configure "$@" '--with-cflags=-DSSH_EXTRAVERSION=\"Debian-7+fips\"'
# Match Debian's configure post-processing: no consumer reads btmp anymore.
sed -i 's/^#define USE_BTMP .*/\/\* #undef USE_BTMP \*\//' config.h
