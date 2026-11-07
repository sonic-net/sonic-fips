# OpenSSH source contract

Configure uses the declared compiler and its system-header flags for both C
compilation and preprocessor probes. Native CI starts without a generated Bazel
lock and retains the regenerated lock, resolved graph and input hashes before
the upstream and package tests.

Large dependency include lists are delivered through GCC14's preprocessor
response-file interface (`-Wp,@file`). This avoids GCC's per-string limit when
its driver creates `COLLECT_GCC_OPTIONS` to start `cc1`; an ordinary driver
`@file` would expand the same oversized environment string. The complete
preprocessing flags retain their order and quoting. Driver and link options
remain in `CFLAGS` and `LDFLAGS`, and invalid driver-only `CPPFLAGS` fail early.
Autoconf retains the response-file path for recursive Make and its preprocessor
probes. Feature options, dependency selections and installed outputs are unchanged.

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

The TAR carries the SONiC Syncd client installation metadata: `usr/bin/ssh-agent`
has mode `2755`, uid 0 and gid 104, the `_ssh` group in that image. All other
entries remain root:root; `ssh-keysign` keeps mode `4755` and the remaining ELF
programs keep `0755`. Image consumers must provide `_ssh` with GID 104 and
preserve these numeric owners and mode bits when adding the TAR. The TAR does
not allocate accounts, so an image using a different `_ssh` GID needs an
explicitly reviewed integration change.

The producer also enables the shipped user socket through
`etc/systemd/user/sockets.target.wants/ssh-agent.socket`, pointing to
`/lib/systemd/user/ssh-agent.socket`, as in the SONiC image. Consumers provide
the merged-/usr `/lib` alias; the target unit is shipped under `usr/lib`.
The existing graphical-session service link and tmpfiles rule, which excludes
`/tmp/ssh-*` from cleanup, remain in the TAR. No host account or service is
modified by this build.

This path assembles a fresh image. It does not perform Debian package upgrades,
configuration-file merging, removal or purge, and it must not invent installed
dpkg records. A consumer retaining APT-managed replacement packages needs a
separate integration contract and validation.

## Build and test

`//openssh:configure_flags_test` exercises the actual adapter with native
GCC14, Autoconf, Autoheader and Make, installed explicitly by the CI workflow.
It reproduces the compiler-to-`cc1` argument-limit failure, then checks real
configure/preprocessor probes, recursive Make, quoted defines, header/link
ordering, prefix maps and identical short/long-flag executable bytes. The full
source builds below use Bazel's declared compiler and dependency toolchains.

Use the native Debian Trixie platform and declared compiler selected by
`.bazelrc`. Build `//openssh:openssh_client_pkg` and
`//openssh:openssh_client_pkg.debug_symbols` for the runtime and matching symbols.
`//openssh:package_test` compares the installed client files with Debian's
manifest, checks all ten native ELF programs and their symbol pairs, and asks
GDB to locate source lines in `ssh` and `ssh-keygen`. It checks the raw TAR's
numeric owners, permission bits and socket enablement link before any consumer
can rewrite their metadata.

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

## Reproducible debug paths

The upstream `configure_make` rule enables `set_file_prefix_map` for the full
execution root. This also normalizes dependency and sysroot header paths, which
are outside the compiler's current source directory. Installed-package tests
reject absolute execution-root paths in the detached symbols while retaining
the existing build-ID, debuglink, source-line and runtime checks.

## Select the source OpenSSL SDK

OpenSSH uses upstream `--with-ssl-dir` to select the declared source OpenSSL
installation. Its native multiarch library directory is also placed before
APT dependency directories in the linker flags. Transitive Debian development
packages can expose a different OpenSSL header version; those headers must
not replace the source SDK while the installed client uses source libcrypto.
The existing strict header/library compatibility check stays enabled.

`//openssh:source_openssl_test` runs the original patched OpenSSH configure
script against source-built OpenSSL runtime, SDK and executable TARs. The
positive case puts a stale header directory earlier in the incoming flags and
requires the selected source prefix to win, including actual linker tracing.
The negative case changes only a private header version and requires the
original mismatch check to reject it with the real source library unchanged.
This bounded configure test disables optional client features; the separate
full production build, original unit/compatibility suite and private-client
smoke retain all existing normal-package features.

## Configure probe runtime

The adapter runs generated Autoconf `conftest` programs through the loader
from the declared build-tools runtime, with source OpenSSL before dependency
libraries. It does not globally export target `LD_LIBRARY_PATH` into host
shells or build utilities. Both generated Autoconf execution sites must match;
a changed generator fails closed instead of silently bypassing feature probes.
The native configure fixture checks both successful and failing runtime probes
in addition to the existing compiler/response-file checks. Its native loader
fixture is not evidence of Ubuntu-host/Trixie-target or ARM compatibility;
those require the separate full source and installed-package checks.
