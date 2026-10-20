# OpenSSH source contract

Configure uses the declared compiler and its system-header flags for both C
compilation and preprocessor probes. Native CI starts without a generated Bazel
lock and retains the regenerated lock, resolved graph and input hashes before
the upstream and package tests.

The SONiC recipe selects `10.0p1-7+fips` and submodule revision
`53e29c05c14ec5f29dbd3df5466b55cf4ca488b1`. The official Debian
[`10.0p1-7` source description](https://deb.debian.org/debian/pool/main/o/openssh/openssh_10.0p1-7.dsc)
records that exact revision in its `Dgit` field. The source rule checks this
record and the SHA-256 hashes of the original source and Debian packaging
archives. It does not substitute the ordinary Debian runtime package. The archive
filename uses `10.0p1`, but its pinned `version.h` identifies the program as
`OpenSSH_10.0p2`; the client smoke test checks that source header.

Apply all 28 Debian patches and the five patches listed in
`src/openssh.patch/series`. The older
`openssh-7.7p1-fips-8.4p1-5.patch` is not selected by Make and remains inactive.
The Microsoft patch needs one context-line refresh for OpenSSH 10.0p1; its
added and removed C lines are unchanged. Applying the SONiC patches before or
after the Debian series produces identical source files.

The active Make recipe does not define `USE_SYMCRYPT_ENGINE`: its direct engine
link options are commented out. Preserve `--with-ssl-engine` and link against
the source-built SONiC OpenSSL target. Provider and engine activation follows
that OpenSSL library and the installed configuration; a `+fips` version suffix
alone is not proof that FIPS mode is enabled or validated.

The image consumer needs the `openssh-client` payload: seven programs in
`usr/bin`, three helper programs in `usr/lib/openssh`, the existing scripts and
configuration. Matching symbols must be split from those same compiled files.
Server, SFTP-server and graphical askpass package coverage must be reported
separately; the client package is the scope needed by the Syncd runtime image.

The runtime TAR contains those client programs, configuration, scripts, user
units, the original tmpfiles rule and copyright notice; manual pages and other
documentation are outside this runtime-only output. OCI consumers add this TAR
directly and add its matching symbols to the debug image. No DEB generation or
Debian metadata helpers are required.

The TAR preserves root ownership and `ssh-keysign` mode `4755`. Image assembly
must also supply the effects of Debian's client post-install script: retain or
create the `_ssh` group, assign its image-specific GID to `usr/bin/ssh-agent`,
and set mode `2755` (or preserve an intentional existing permission override).
The image owns group allocation, so the component TAR leaves `ssh-agent` at
root:root `0755`; extracting it alone does not complete that installation step.
Keep the shipped user units and tmpfiles rule, which excludes `/tmp/ssh-*` from
cleanup. No host account or service is modified by this build.

This path assembles a fresh image. It does not perform Debian package upgrades,
configuration-file merging, removal or purge, and it must not invent installed
dpkg records. A consumer retaining APT-managed replacement packages needs a
separate integration contract and validation.

## Build and test

Use the native Debian Trixie platform and declared compiler selected by
`.bazelrc`. Build `//openssh:openssh_client_pkg` and
`//openssh:openssh_client_pkg.debug_symbols` for the runtime and matching symbols.
`//openssh:package_test` compares the installed client files with Debian's
manifest, checks all ten native ELF programs and their symbol pairs, and asks
GDB to locate source lines in `ssh` and `ssh-keygen`.

`//openssh:upstream_tests_debug` runs the original `unit` and `compat-tests`
targets, then checks the built clients with a temporary key and a private
foreground SSH agent. It uses neither an SSH server nor host credentials.
CI requires its `client-smoke.json` success receipt; a failed directory change
cannot silently skip the smoke check.
The test action is excluded from the shared disk/remote cache; CI uses a fresh
Bazel output base so it executes on each native runner.

The OpenSSH workflow runs both checks on native AMD64 and ARM64 machines. Its
artifacts contain both TARs, source and patch records, action audit, source build
logs and test receipts. It builds no Debian packages. The source-built OpenSSL
provider/engine integration and final image behavior need their own validation;
these default-mode client tests do not certify FIPS operation.
