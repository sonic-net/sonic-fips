# Kerberos runtime libraries

SONiC's base image consumes four Kerberos packages at `1.21.3-5+fips`:
`libk5crypto3`, `libkrb5support0`, `libkrb5-3` and `libgssapi-krb5-2`.
The owner repository's `rules/krb5.mk` names only `libk5crypto3`; this build
follows the four-package contract in sonic-buildimage's `FIPS_KRB5_ALL` and
`docker-base-trixie` dependencies. The `libkrb5-3` package also contains the
SPAKE preauthentication plugin, documentation and its plugin directory.

The build uses checksum-pinned Debian `1.21.3-5` source archives and source
description, applies all 13 Debian patches, and preserves SONiC's OpenSSL
crypto selection and two test patches. The crypto-selection patch needs only
surrounding Debian-rule context refreshed for this version.

The selected Salsa submodule commit is
`d26e8df8ee220af0f2361a66d2d357762aff1c3e`. Its archive was unavailable during
implementation, and the Debian source description has no `Dgit` field. The
archive version matches the recipe; equivalence to that exact Git tree remains
unverified and is recorded in `source.json`.

The normal Debian configure features remain enabled: system error/command
libraries, LDAP, LMDB, libverto, shared libraries and the OpenSSL crypto
implementation. The build uses SONiC's source OpenSSL and declared
`compile_et`, `mk_cmds`, Autoconf, Perl, Bison and pkgconf tools. Original Debian
pkg-config metadata supplies dependency information; only installation path
variables are relocated for the build directory.

## Outputs and validation

| Runtime TAR target | Contents |
| --- | --- |
| `//krb5:libk5crypto3_pkg` | Crypto library and runtime link |
| `//krb5:libkrb5support0_pkg` | Support library and runtime link |
| `//krb5:libkrb5_3_pkg` | Kerberos library, SPAKE plugin, runtime link and docs |
| `//krb5:libgssapi_krb5_2_pkg` | GSS API library, runtime link and mechanism directory |

Each target has a `.debug_symbols` target containing matching build-ID debug
files for a container's separate debug layer. All four retain copyright notices.
The libraries and plugin have mode `0644` and root ownership.

`//krb5:crypto_tests_debug` runs the original `lib/crypto/crypto_tests` checks
without starting KDC or network services. The test action explicitly supplies
the source OpenSSL library path, verifies it in a dynamic-loader trace, and
writes a required `crypto-tests.json` receipt. Production package builds do
not run those tests as a side effect.

`//krb5:package_test` checks exact installed file/link inventories, native
architecture, runtime library names, Debian versioned symbols and all five
ELF/debug pairs. It loads the installed libraries and SPAKE plugin with the
source OpenSSL TAR, exercises random-byte generation, Kerberos context
creation and GSS mechanism discovery, and checks GDB source lookup.

OCI consumers add these runtime TARs directly and collect their matching
`.debug_symbols` outputs in the debug layer. This path needs no DEB generation,
Debian metadata helpers or synthetic installed-package records, and does not
migrate KDC/server packages.

The runtime links and GSS mechanism directory are explicit TAR entries. The
historical GSS maintainer scripts handle old installation upgrades and purge;
assembling a fresh OCI filesystem does not perform those package lifecycle
operations. The final image must independently validate library loading, its
complete dependency set, provider configuration and service behavior. Consumers
retaining APT-managed replacement packages need their own integration contract.
Native AMD64 and ARM64 CI retains packages, source checksums, module resolution,
action audits and test evidence. This is not a FIPS certification claim.
