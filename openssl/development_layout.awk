# Preserve Debian's libssl-dev.install and multiarch header layout. tar.bzl
# still owns mtree generation, ownership/time normalization and TAR assembly.
{
    if ($1 ~ /(^|\/)debian\/copyright$/) {
        $1 = "usr/share/doc/libssl-dev/copyright"
    } else {
        sub(/^openssl\/copy_build\/build\//, "", $1)
        if ($1 ~ /^usr\/include\/openssl\//) {
            if ($1 ~ /\/(configuration|opensslconf)\.h$/)
                sub(/^usr\/include\//, "usr/include/" multiarch "/", $1)
        } else if ($1 ~ ("^usr/lib/" multiarch "/(libcrypto|libssl)\\.so$")) {
            # The install tree's linker names are relative symlinks. Do not
            # duplicate the versioned runtime library into the dev package.
            name = $1
            sub(/^.*\//, "", name)
            $0 = $1 " type=link mode=0777 uid=0 gid=0 time=1787585182 link=" name ".3"
        } else if ($1 !~ ("^usr/lib/" multiarch "/((libcrypto|libssl)\\.a$|pkgconfig/|cmake/OpenSSL/)")) {
            next
        }
    }
    # Match dh_fixperms. Bazel's materialized tree can mark cached files
    # executable even though installed headers and archives are data files.
    if ($0 ~ /type=file/)
        sub(/mode=[0-7]+/, "mode=0644")
}

@include "default"
