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
# Use libedit's declared metadata instead of configure's guessed -lcurses
# fallback. Reuse the Kerberos adapter's isolated metadata staging; CcInfo
# continues to supply the actual target headers and libraries.
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
# OpenSSH invokes "$PKGCONFIG" as one executable, not a shell command.
# Keep the declared tool and its prefix overrides separate, including paths
# with spaces. The launcher inherits only the isolated metadata lookup above.
# CcInfo already supplies the shared SDK root as a system include. Do not let
# libedit's generic -I promote its OpenSSL headers ahead of the source owner;
# retain package-specific includes and keep this filtering local to pkgconf.
export SONIC_LIBEDIT_PKGCONF="$PKGCONFIG"
pkgconf_launcher="$PWD/.bazel-pkgconf"
printf '%s\n' '#!/bin/sh' 'set -eu' \
    'unset PKG_CONFIG_ALLOW_SYSTEM_CFLAGS' \
    'export PKG_CONFIG_SYSTEM_INCLUDE_PATH="$EXT_BUILD_DEPS/include/usr/include"' \
    'exec "$SONIC_LIBEDIT_PKGCONF" "--define-variable=prefix=$EXT_BUILD_DEPS" "--define-variable=libdir=$EXT_BUILD_DEPS/lib" "--define-variable=includedir=$EXT_BUILD_DEPS/include/usr/include" "$@"' \
    > "$pkgconf_launcher"
chmod +x "$pkgconf_launcher"
export PKGCONFIG="$pkgconf_launcher"
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
# Report only the failed libedit link check, before Autoconf's program/cache
# dumps. Bound each line as dependency flags can be tens of kilobytes long.
# A subshell isolates diagnostic write errors from configure's original status.
report_libedit_link_failure() (
    LC_ALL=C
    export LC_ALL
    test -r config.log || return 0
    probe_active=false
    probe_capture=false
    probe_excerpt=
    probe_lines=0
    probe_bytes=0
    while IFS= read -r probe_line || test -n "$probe_line"; do
        case "$probe_line" in
            configure:*": checking for el_init in -ledit")
                probe_active=true
                probe_capture=true
                ;;
        esac
        test "$probe_active" = true || continue
        case "$probe_line" in
            "configure: failed program was:") probe_capture=false ;;
            configure:*": result: no")
                printf '%s\n%s' 'OpenSSH failed libedit link probe (bounded config.log excerpt):' "$probe_excerpt"
                return 0
                ;;
            configure:*": result: "*) return 0 ;;
        esac
        test "$probe_capture" = true || continue
        # No environment/credential values are useful to this link diagnostic.
        case "$probe_line" in
            *TOKEN*|*token*|*PASSWORD*|*password*|*SECRET*|*secret*|*Authorization:*|*://*)
                probe_line='[sensitive or URL-bearing line omitted]'
                ;;
        esac
        if test "${#probe_line}" -gt 2048; then
            probe_line="$(printf '%.2048s' "$probe_line") [line clipped]"
        fi
        probe_lines=$((probe_lines + 1))
        probe_bytes=$((probe_bytes + ${#probe_line} + 1))
        if test "$probe_lines" -le 32 && test "$probe_bytes" -le 16384; then
            probe_excerpt="$probe_excerpt$probe_line
"
        fi
    done < config.log
    return 0
)
# Debian's extra version identifies the same source/patch set as the Make build.
if ./configure "$@" '--with-cflags=-DSSH_EXTRAVERSION=\"Debian-7+fips\"'; then
    :
else
    configure_status=$?
    report_libedit_link_failure >&2 || :
    exit "$configure_status"
fi
# Match Debian's configure post-processing: no consumer reads btmp anymore.
sed -i 's/^#define USE_BTMP .*/\/\* #undef USE_BTMP \*\//' config.h
