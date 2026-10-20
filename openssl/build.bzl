"""Shared vendor build configuration for OpenSSL packages and integration tests."""

load("@rules_foreign_cc//foreign_cc:defs.bzl", "configure_make")

_LIBDIR = select({
    "@platforms//cpu:x86_64": "usr/lib/x86_64-linux-gnu",
    "@platforms//cpu:aarch64": "usr/lib/aarch64-linux-gnu",
})

def openssl_build(name, **overrides):
    """Build the Make-selected OpenSSL source; allow test-only extra inputs."""
    attributes = dict(
        args = [
            "-j4",
            "DESTDIR=$$BUILD_TMPDIR$$/$$INSTALL_PREFIX$$",
        ],
        build_data = ["@sonic_build_infra//tools/build_tools:configure_runtime"],
        configure_command = "Configure",
        configure_in_place = True,
        configure_options = [
            "shared",
            "--prefix=/usr",
            "--openssldir=/usr/lib/ssl",
            "no-idea",
            "no-mdc2",
            "no-rc5",
            "no-ssl3",
            "enable-unit-test",
            "no-ssl3-method",
            "enable-rfc3779",
            "enable-cms",
            "no-capieng",
            "no-rdrand",
            "enable-tfo",
            "enable-zstd",
            "enable-zlib",
            "enable-fips",
            "enable-ec_nistp_64_gcc_128",
        ] + select({
            "@platforms//cpu:x86_64": [
                "debian-amd64",
                "--libdir=lib/x86_64-linux-gnu",
            ],
            "@platforms//cpu:aarch64": [
                "debian-arm64",
                "--libdir=lib/aarch64-linux-gnu",
                "no-padlockeng",
            ],
        }),
        configure_prefix = "$$EXT_BUILD_ROOT$$/$(execpath @sonic_build_infra//tools/build_tools:configure_runtime)/bin/perl",
        env = {
            "CFLAGS": "-ffile-prefix-map=$$EXT_BUILD_ROOT$$=.",
            # Build-time Perl is declared; installed scripts use the target's Perl.
            "HASHBANGPERL": "/usr/bin/perl",
            "PERL": "$(execpath @sonic_build_infra//tools/build_tools:configure_runtime)/bin/perl",
            # Match Make's Debian changelog timestamp plus one day.
            "SOURCE_DATE_EPOCH": "1787585182",
        },
        features = ["-sanitize_pwd"],
        lib_source = "@openssl_src//:sources",
        out_bin_dir = "usr/bin",
        out_binaries = ["openssl"],
        out_data_files = [
            "usr/bin/c_rehash",
            "usr/lib/ssl/openssl.cnf",
            "usr/lib/ssl/misc/CA.pl",
            "usr/lib/ssl/misc/tsget.pl",
        ] + select({
            "@platforms//cpu:x86_64": [
                "usr/lib/x86_64-linux-gnu/engines-3/afalg.so",
                "usr/lib/x86_64-linux-gnu/engines-3/loader_attic.so",
                "usr/lib/x86_64-linux-gnu/engines-3/padlock.so",
            ],
            "@platforms//cpu:aarch64": [
                "usr/lib/aarch64-linux-gnu/engines-3/afalg.so",
                "usr/lib/aarch64-linux-gnu/engines-3/loader_attic.so",
            ],
        }),
        out_include_dir = "usr/include",
        out_lib_dir = _LIBDIR,
        out_shared_libs = [
            "libcrypto.so.3",
            "libssl.so.3",
        ],
        targets = [
            "build_sw",
            "install_sw",
            "install_ssldirs",
        ],
        deps = [
            "@openssl_deps//libzstd-dev:libzstd",
            "@openssl_deps//zlib1g-dev:zlib1g",
        ],
    )
    attributes.update(overrides)
    configure_make(name = name, **attributes)
