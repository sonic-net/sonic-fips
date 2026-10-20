"""Fetch the OpenSSH source associated with SONiC's exact Debian git pin."""

_PATCHES = [
    "0001-Put-style-as-line-number-to-ssh-session-environment-.patch",
    "0002-Revert-commit-69334996-make-sshd_config-ClientAliveC.patch",
    "0003-Export-remote-info-for-authorization.patch",
    "0004-Remove-second-pwnam-call.patch",
    "microsoft-symcrypt-fips.patch",
]

def _openssh_source_impl(ctx):
    ctx.download(
        url = "https://deb.debian.org/debian/pool/main/o/openssh/openssh_10.0p1-7.dsc",
        output = "openssh.dsc",
        sha256 = "67fee78460ebb9adbe75726dc764360886dec4721cd3d10217bd0d071db0badb",
    )
    if "Dgit: 53e29c05c14ec5f29dbd3df5466b55cf4ca488b1 " not in ctx.read("openssh.dsc"):
        fail("Debian source description does not identify the SONiC submodule revision")
    ctx.download_and_extract(
        url = "https://deb.debian.org/debian/pool/main/o/openssh/openssh_10.0p1.orig.tar.gz",
        sha256 = "021a2e709a0edf4250b1256bd5a9e500411a90dddabea830ed59cef90eb9d85c",
        stripPrefix = "openssh-10.0p1",
    )
    ctx.download_and_extract(
        url = "https://deb.debian.org/debian/pool/main/o/openssh/openssh_10.0p1-7.debian.tar.xz",
        sha256 = "09888aeb70db929b83f6acf8439f9de43c69ef7de89bb2f9549ef1bff5688fc5",
    )
    selected = [
        line.strip()
        for line in ctx.read(ctx.attr.series).splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if selected != _PATCHES:
        fail("SONiC's OpenSSH patch series changed; update the source contract")

    # Match Make's SONiC series followed by the Debian package source series.
    # Both orders were independently checked to produce the same source files.
    for patch in ctx.attr.sonic_patches:
        ctx.patch(patch, strip = 1)
    debian_patches = []
    for line in ctx.read("debian/patches/series").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if " " in line or "\t" in line:
            fail("Unexpected Debian patch options: " + line)
        ctx.patch(ctx.path("debian/patches/" + line), strip = 1)
        debian_patches.append(line)
    ctx.file("bazel-configure", ctx.read(ctx.attr.configure), executable = True)
    ctx.file("source.json", json.encode_indent({
        "_generated": {"notice": "AUTO-GENERATED. DO NOT EDIT MANUALLY.", "generator": "sonic-fips //openssh:sources.bzl"},
        "version": "10.0p1-7+fips",
        "debian_source_version": "1:10.0p1-7",
        "debian_package_version": "1:10.0p1-7+fips",
        "dgit": "53e29c05c14ec5f29dbd3df5466b55cf4ca488b1",
        "sonic_patches": selected,
        "debian_patches": debian_patches,
    }) + "\n")
    ctx.file("BUILD.bazel", """# AUTO-GENERATED. DO NOT EDIT MANUALLY.
# Generator: sonic-fips //openssh:sources.bzl
filegroup(
    name = "sources",
    srcs = glob(["**"], exclude = ["BUILD.bazel"]),
    visibility = ["//visibility:public"],
)
exports_files([
    "source.json", "debian/rules", "debian/openssh-client.install",
    "contrib/ssh-copy-id", "debian/ssh-argv0", "debian/openssh-client.apport",
    "debian/systemd/ssh-agent.service", "debian/systemd/ssh-agent.socket",
    "debian/copyright", "debian/openssh-client.tmpfiles",
])
""")

openssh_source = repository_rule(
    implementation = _openssh_source_impl,
    attrs = {
        "series": attr.label(default = "//src/openssh.patch:series"),
        "configure": attr.label(default = "//openssh:configure.sh"),
        "sonic_patches": attr.label_list(default = ["//src/openssh.patch:" + p for p in _PATCHES]),
    },
)
