# Generated FIPS package metadata

`//:runtime_packages.json` combines generated metadata from OpenSSL, Kerberos,
OpenSSH and SymCrypt. Each component's BUILD file maps Debian package names to
its existing runtime TARs. Package fields come from the same prepared Debian
control and changelog files used by that source recipe. The prepared changelogs
apply the existing Makefile's `+fips` version suffix; no second package version
or dependency list is maintained here.

SymCrypt already has a finalized Debian control file containing its version, so
that existing file is used directly. The metadata action still calculates native
library requirements from its actual TAR. Source-built dependencies supply
their generated library metadata; pinned APT dependencies supply their package
controls and payloads. These target libraries are separate from execution tools.

The output follows the selected AMD64/ARM64 build. The image consumes this JSON,
the corresponding runtime TARs and selected MODULE declaration, validating the
owner targets and recording the actual payload hashes. Generating metadata does
not build a Debian package or run installation scripts. Legacy Make recipes are
unchanged.
