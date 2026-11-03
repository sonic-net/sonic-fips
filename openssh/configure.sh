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
"$AUTOCONF"
"$AUTOHEADER"
mkdir -p .pkgconfig-empty
export PKG_CONFIG_LIBDIR="$PWD/.pkgconfig-empty"
export PKG_CONFIG_PATH=
# Autoconf's preprocessor probes omit CFLAGS. Keep the declared compiler's
# system-header flags instead of falling back to the runner's /lib/cpp.
export CPP="$CC ${CFLAGS:-} -E"
# Debian's extra version identifies the same source/patch set as the Make build.
./configure "$@" '--with-cflags=-DSSH_EXTRAVERSION=\"Debian-7+fips\"'
# Match Debian's configure post-processing: no consumer reads btmp anymore.
sed -i 's/^#define USE_BTMP .*/\/\* #undef USE_BTMP \*\//' config.h
