# OpenSSL runtime and debug TARs

This build uses the OpenSSL and Debian source versions selected by
[`rules/openssl.mk`](../rules/openssl.mk): **3.5.7-1~deb13u2**, with SONiC's
existing FIPS integration patches. It produces runtime and debug TARs for
container layers.

## Source and build contract

[`sources.bzl`](sources.bzl) downloads the upstream source archive and Debian
source patch archive with the SHA-256 values in Debian's published
`openssl_3.5.7-1~deb13u2.dsc`. It applies the same order as Make:

1. The two active SONiC runtime patches in `src/openssl.patch/series`.
2. All 23 patches in Debian's source series, including its security fixes.
3. The four SONiC test patches added to the Debian series by Make.

The two runtime patches have refreshed surrounding lines for OpenSSL 3.5.7.
Their resulting source is byte-for-byte identical to applying the original
patches through Make's GNU patch/quilt behavior. No cryptographic logic changes.

`rules_foreign_cc` runs the vendor's Configure and Make targets with declared
GCC, Make and Perl tools. Configure keeps Debian's architecture target and
feature switches, including FIPS, zlib and zstd support. `--prefix=/usr` and
`--openssldir=/usr/lib/ssl` describe the installed system; `DESTDIR` stages the
files privately in the Bazel action. Generated Perl scripts retain
`#!/usr/bin/perl` for the installed system. The build uses Make's fixed source
timestamp. Compiler prefix maps remove the private build-directory prefix from
debug information.

The source supports native AMD64 and ARM64 on Debian Trixie. ARM64 omits the
x86 PadLock engine, as Debian's build does.

## Public targets

| Target | Consumer |
| --- | --- |
| `//openssl:build` | C/C++ consumers needing generated headers, `libcrypto.so.3` and `libssl.so.3` |
| `//openssl:libssl3t64_pkg` | Runtime libraries and the architecture's engine plugins |
| `//openssl:libssl3t64_pkg.debug_symbols` | Matching DWARF symbols for those exact libraries |
| `//openssl:openssl_pkg` | The OpenSSL command, helper scripts and runtime configuration |
| `//openssl:openssl_pkg.debug_symbols` | Matching symbols for the command |
| `//openssl:libssl_dev_pkg` | Headers, static libraries, linker symlinks, pkg-config and CMake metadata used in the base container |

Runtime ELF files are stripped through the shared `sonic_deploy_tar` rule;
separate symbols use the same build IDs. Engine plugins are additional build
outputs, so linking a C/C++ consumer does not link every plugin into it.
The OCI consumer adds these TARs directly as filesystem layers. This source
build has no Debian package-generation step or dependency on Debian metadata
helpers. Importing pinned Debian development libraries for compilation remains
a separate external-input step.

The TARs retain the configured paths, ownership, permissions, symlinks and
matching symbols. Image assembly owns system integration such as the CA trust
store and dynamic-loader cache. These TARs do not create or update dpkg records;
a consumer that promises APT-managed replacement packages needs its own explicit
package-management integration.

The development archive reuses that same build's install tree and Debian's
`libssl-dev.install` file selection. As in Debian's `debian/rules`, its two
configuration headers move to `/usr/include/<multiarch>/openssl` so different
architectures can coexist. It does not change the SDK's C/C++ linking preference
or duplicate the runtime shared libraries. Its static archives retain the
source build's debug information; runtime ELF symbols remain separate.

The SONiC mode-selection behavior and SymCrypt integration remain the original
project code. These build targets alone do not establish FIPS certification;
SymCrypt producer validation and final image integration are separate required
work.

## Validation

`//openssl:package_test` checks the installed command, library loading, runtime
paths, matching build IDs and debug-link checksums, and GDB source lookup.
It also compiles and runs small shared and static consumers using the installed
development archive. GCC, pkg-config and zlib/zstd development files are explicit
native test prerequisites; producer compilation still uses the Bazel toolchain.

Each native CI job starts without a Bazel lockfile, generates it in update mode,
and uploads it with the resolved module graph and hashes of the declared inputs.
`MODULE.bazel.lock` remains ignored. These records are retained before the
package test so a failed build still leaves its selected dependencies available
for diagnosis.

The full OpenSSL suite also needs the SymCrypt engine and provider: SONiC's
existing test patch copies them before running its tests. Those components link
against OpenSSL, so the core build cannot depend on their test setup. A separate
integration test must supply their declared source-build outputs. This full-suite
integration remains pending while that producer is migrated; a core package
check does not establish that the full suite passed.

## Shared package imports

Distroless package imports use the published `rules_distroless`
`0.9.4.sonic.6` module and the Debian GCC toolchains in `sonic-build-infra`
`0.0.17-8baf1ad829c5095297d85148b042145b87d623a3`. Both are selected from the
maintained SONiC registry `main` endpoint in local builds and CI. These landed
replacements preserve normal ELF RUNPATH handling without the superseded
transitive RPATH workaround.

CI records the observed registry revision, effective Bazel configuration,
resolved module graph and generated lockfile. Reproduce the native check with:

```sh
python3 tools/bazel/registry_inputs.py artifacts/openssl
python3 tools/bazel/ci.py --architecture amd64 --artifacts artifacts/openssl
```

The action audit rejects Debian package production before executing the tests.
