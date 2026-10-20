"""Prepare the Debian Krb5 source version selected by SONiC's package recipe."""

_DEBIAN_PATCHES = [
    "debian-local/0001-Debian-HURD-compatibility.patch",
    "debian-local/0002-debian-Handle-multi-arch-paths-in-krb5-config.patch",
    "debian-local/0003-debian-osconf.hin-path-changes.patch",
    "debian-local/0004-debian-install-ldap-library-in-subdirectory.patch",
    "debian-local/0005-gssapi-never-unload-mechanisms.patch",
    "debian-local/0006-Add-substpdf-target.patch",
    "debian-local/0007-Fix-pkg-config-library-include-paths.patch",
    "debian-local/0008-Use-isystem-for-include-paths.patch",
    "0009-Add-.gitignore.patch",
    "0011-Allow-kpropd-to-bind-even-if-only-loopback-is-config.patch",
    "0012-Skip-keyring-tests-if-keyring-blocked-by-seccomp.patch",
    "0012-Replace-ssl.wrap_socket-for-tests.patch",
    "CVE-2025-24528.patch",
]

def _series(text):
    return [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]

def _krb5_source_impl(ctx):
    ctx.download(
        url = "https://snapshot.debian.org/file/de2952906b70cbb9db4df107f788241c707b99d4",
        output = "krb5.dsc",
        sha256 = "88e736b6439d0fe30317ae7c38c3093b7139f1b7709997debe28d756f92de353",
    )
    if "\nVersion: 1.21.3-5\n" not in ctx.read("krb5.dsc"):
        fail("Unexpected Debian source version")
    ctx.download_and_extract(
        url = "https://snapshot.debian.org/file/3e383bbe88cbed56bdad4ba655c40abf0e961cf7",
        type = "tar.gz",
        sha256 = "b7a4cd5ead67fb08b980b21abd150ff7217e85ea320c9ed0c6dadd304840ad35",
        stripPrefix = "krb5-1.21.3",
    )
    ctx.download_and_extract(
        url = "https://snapshot.debian.org/file/6796cf7d9aa28564b70b6066e158a9d52f736fde",
        type = "tar.xz",
        sha256 = "521fdfaf5cda93a64cc70afd357dc31ea6f4128ff5a489b036b58887eceddd46",
    )
    if _series(ctx.read("debian/patches/series")) != _DEBIAN_PATCHES:
        fail("Debian patch series changed")
    for name in _DEBIAN_PATCHES:
        ctx.patch(ctx.path("debian/patches/" + name), strip = 1)
    if _series(ctx.read(ctx.attr.series)) != ["90-support-openssl-crypto-impl.patch"]:
        fail("SONiC crypto selection changed")
    ctx.patch(ctx.attr.crypto_patch, strip = 1)
    if _series(ctx.read(ctx.attr.test_series)) != ["fix-test-output.patch", "fix-running-in-container.patch"]:
        fail("SONiC test patch series changed")
    for patch in ctx.attr.test_patches:
        ctx.patch(patch, strip = 1)
    ctx.file("src/bazel-configure", ctx.read(ctx.attr.configure), executable = True)
    ctx.file("source.json", json.encode_indent({
        "_generated": {"notice": "AUTO-GENERATED. DO NOT EDIT MANUALLY.", "generator": "krb5/sources.bzl"},
        "version": "1.21.3-5+fips",
        "debian_source_version": "1.21.3-5",
        "sonic_gitlink": "d26e8df8ee220af0f2361a66d2d357762aff1c3e",
        "git_tree_equivalence": "not verified: the Debian DSC has no Dgit field and the Salsa gitlink was unavailable",
        "debian_patches": _DEBIAN_PATCHES,
        "sonic_patches": ["90-support-openssl-crypto-impl.patch", "fix-test-output.patch", "fix-running-in-container.patch"],
        "crypto_implementation": "openssl",
    }) + "\n")
    ctx.file("BUILD.bazel", """# AUTO-GENERATED. DO NOT EDIT MANUALLY.
# Generator: krb5/sources.bzl
exports_files(["source.json", "debian/rules", "debian/libk5crypto3.install", "debian/libk5crypto3.symbols", "debian/copyright", "README", "debian/README.Debian", "debian/libkrb5support0.symbols", "debian/libkrb5-3.symbols", "debian/libgssapi-krb5-2.symbols"])
""")
    ctx.file("src/BUILD.bazel", """# AUTO-GENERATED. DO NOT EDIT MANUALLY.
# Generator: krb5/sources.bzl
filegroup(name = "sources", srcs = glob(["**"], exclude = ["BUILD.bazel"]), visibility = ["//visibility:public"])
""")

krb5_source = repository_rule(
    implementation = _krb5_source_impl,
    attrs = {
        "configure": attr.label(default = "//krb5:configure.sh", allow_single_file = True),
        "series": attr.label(default = "//src/krb5.patch:series", allow_single_file = True),
        "crypto_patch": attr.label(default = "//src/krb5.patch:90-support-openssl-crypto-impl.patch", allow_single_file = True),
        "test_series": attr.label(default = "//src/krb5.patch:debian.patch/series", allow_single_file = True),
        "test_patches": attr.label_list(default = ["//src/krb5.patch:debian.patch/fix-test-output.patch", "//src/krb5.patch:debian.patch/fix-running-in-container.patch"]),
    },
)
