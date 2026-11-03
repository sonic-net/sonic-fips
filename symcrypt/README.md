# SymCrypt and its OpenSSL engine/provider

The Bazel build follows `src/SymCrypt-OpenSSL-Debian/Makefile` for native Trixie
AMD64 and ARM64. It builds the exact public submodules selected by sonic-fips:

| Input | Revision |
| --- | --- |
| SymCrypt 103.13.0 | `286762b7730e2b780678f5ab11fef2b1bad639e0` |
| SymCrypt-OpenSSL 1.11.0 | `60d89642fcd042d099bc57e48e2e8381e9671899` |
| jitterentropy-library | `887c9871ea110e397812ff7f3b28a6269f0a2ffc` |
| pyelftools 0.29, used by the integrity script | `15f032b22a9b870b66d3238822724addda643ca3` |

`sources.bzl` pins each source archive's checksum. The private legacy test
dependency remains disabled, matching upstream's default. No Debian package is
produced by these targets.

## Public targets

| Target | Output |
| --- | --- |
| `//symcrypt:core` | Declared core headers, shared library and upstream unit-test executable |
| `//symcrypt:provider` | OpenSSL engine/provider linked with `//openssl:build` and the source-built core |
| `//symcrypt:runtime` | Runtime filesystem TAR for OCI layers |
| `//symcrypt:runtime.debug_symbols` | Matching symbols for all three installed ELF files |
| `//symcrypt:package_test` | Installed files, symbols, self-tests, integrity enforcement and OpenSSL consumers |

The runtime keeps native library names and engine/provider locations under
`/usr/lib/<multiarch>`, including the original four symbolic links and `/etc/ssl`.
The runtime TAR includes all three source-license notices.

OCI consumers take `//symcrypt:runtime` directly and collect the matching symbols
through `//symcrypt:runtime.debug_symbols`. No DEB archive or Debian metadata
generator is needed. The original Make packaging remains available separately.

## Compiler and build behavior

The core uses upstream `toolchains_llvm` 1.11.2 with Clang 19.1.7, matching the
upstream version of the native SONiC Trixie builder's Debian Clang package. Debian
compiler packaging patches are not claimed to be identical. The standard
`cmake_variant` rule scopes Clang to the core. Its linker, strip and objcopy are
the existing declared SONiC GNU tools (Binutils 2.46.0.20260210 in this toolchain). The OpenSSL engine/provider retain native
GCC and consume OpenSSL's declared generated headers and shared libraries.

The small `toolchain.bzl` extension calls upstream's public `llvm_toolchain`
macro because upstream's own module extension accepts only a root module. This
keeps the same maintained compiler implementation usable when an image consumes
`sonic-fips` as a dependency, without registering LLVM for other components.

Clang and GCC share the published multiarch `sonic_sysroot` repository, including
the pinned Debian headers and GCC development-library runtime dependencies.
The core preserves upstream's warning policy by removing LLVM's additional `-Wall`, `-Wthread-safety`, and
`-Wself-assign` defaults before applying the unchanged upstream CMake settings.
ASM, release optimization, FIPS self-tests, integrity postprocessing, binary
stripping and the upstream unit tests remain enabled. ARM64 retains
`-mno-outline-atomics`. No SymCRust dependency is introduced.

The assembly-flags patch appends upstream's assembler language mode to the
existing declared flags, preserving the execution-root prefix map. Generated
assembly therefore uses the same source/debug path mapping as C before the
original strip-and-seal sequence. CI checks actual assembly command lines and
the original core debug file for worker paths. The random integrity key and
build timestamp remain separate sources of non-identical core bytes.

The small declared-tools patch selects CMake's explicit Make, archive, strip and
objcopy programs, and passes the declared link flags to jitterentropy. The
upstream crypto sources, export script and integrity algorithm are unchanged.
CMake copies declared source files into a private writable directory because
upstream's generators write headers and jitterentropy outputs beside the source.
This copy dereferences Bazel's input symlinks.

## Sealed module and debug symbols

Upstream extracts debug information, strips the module, then calculates its
integrity digest. The sealed `libsymcrypt.so.103.13.0` enters the TAR as unchanged
data: it receives no later stripping, RPATH editing or debuglink insertion. Its
original debug file is installed by build ID, which GNU GDB can discover directly.
The engine and provider use the shared normal split-debug packaging rules.
`runtime` publishes all three symbol trees through the shared `DebugSymbolsInfo`
provider. Its `runtime.debug_symbols` target uses the standard OCI
`debug_symbols_layer`, so downstream images collect the core symbols through the
same API as other native libraries.

Upstream generates a random, nonsecret integrity key; clean rebuilds therefore
need not produce identical module bytes. Build metadata uses the pinned SymCrypt
commit timestamp (`SOURCE_DATE_EPOCH=1785966537`, matching `2026-08-05T21:48:57Z`)
so the generated `buildInfo.h` header does not vary by wall clock or host time
zone, while `symcrypt_internal_shared.inc` retains upstream's random key.
`//symcrypt:timestamp_test` runs the actual generator across build roots, time
zones, edited epochs and invalid input. The package test also requires
the installed module to equal the particular sealed build output, verifies its
matching symbols, loads it to execute upstream startup self-tests, and checks
that changing one digest byte in a disposable copy causes upstream's fatal
integrity rejection. This Bazel rebuild makes no certification claim.

CMake does not insert a temporary build RPATH into the engine or provider.
Its normal install-time removal otherwise leaves path-length-dependent padding
in the ELF dynamic string table: the FRR image's local and hosted builds had
identical code and DWARF, but 44 different trailing NUL bytes and consequently
different build IDs. `CMAKE_SKIP_RPATH=ON` prevents that padding at link time;
installed consumers already use their declared library paths. The core's
random integrity key and HMAC remain unchanged, so whole runtime/debug TAR
reproducibility is not claimed.

## Validation and maintenance

Run `bazel test //symcrypt:package_test` after auditing that target's action graph.
AMD64 CI also runs `tools/bazel/provider_repro.py`: two genuine upstream
CMake actions share the public build contract, but use fresh output bases
with different-length paths. Only this private producer disables action-cache
reuse; core/OpenSSL dependencies keep their normal cache behavior. Complete
unstripped engine/provider ELFs, including DWARF, must be byte-identical.

Native AMD64 and ARM64 CI retains runtime/debug TARs, their hashes, the module
graph and lock, compiler commands, CMake settings and build logs. The test also
runs the original full SymCrypt unit-test executable, an explicit provider SHA256
operation and engine loading plus SHA256 through source-built OpenSSL.
CI also analyzes the complete package-test graph from `tests/consumer`, a separate
downstream module, to reject compiler extensions that only work at the source root.

The component test uses `OPENSSL_CONF=/dev/null` so it selects the installed
engine/provider explicitly. Automatic activation through the final SONiC FIPS
configuration and the complete provider-dependent OpenSSL suite belong to the
downstream integration validation. ARMHF and cross-compilation are outside this
native AMD64/ARM64 target contract.

When updating a submodule, update its archive pin, source version and known output
names together. Keep the integrity ordering and original symbol file intact, and
run the native package test on both CPUs before changing downstream image pins.
