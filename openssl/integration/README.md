# Original OpenSSL tests with source-built plugins

SONiC patches OpenSSL's original `make test` recipe to copy the SymCrypt engine
and provider from `libdir`. The production OpenSSL build cannot depend on those
plugins because they link OpenSSL themselves. This downstream test target
builds the original suite separately, using the same build configuration and
the source-built plugins from `//symcrypt:runtime`, a filesystem TAR:

```sh
bazel test //openssl/integration:openssl_symcrypt_test --nocache_test_results
```

The test copies only the required files into a private directory and supplies
that directory as `libdir`. The integrity-sealed SymCrypt core is copied
verbatim. No host library directory or FIPS activation file is changed.
TAP, Perl's test runner, normally passes source modules through `PERL5LIB`.
The declared Perl launcher clears that variable to avoid loading host modules.
A private `HARNESS_PERL` adapter passes only OpenSSL's declared `util/perl`
directory with `-I`. The sealed core also sits beside the test build's shared
libraries, where OpenSSL's existing loader wrapper can find it even after Perl
clears inherited library paths. Neither adapter changes a crypto test.

Production runtime/debug TARs keep the same build arguments, targets and outputs; their
configuration was moved into `//openssl:build.bzl` so the test cannot silently
choose a different algorithm set.

The native AMD64 and ARM64 workflow runs this explicit target in a fresh
container. The test action excludes remote/disk reuse of its suite result;
normal dependency builds can use cache. TAP uses its supported four-worker
scheduling mode; no test selection is changed. It preserves the original harness log,
recipe/test counts, source/dependency resolution and the packaged plugin TAR's
checksum. A failed Make test fails the build, and the receipt also requires the
harness's final result to be `PASS`. No new skip list or test patch is applied.

This is the ordinary-mode vendor suite with the plugins available. Explicit
engine/provider operations are also covered by `//symcrypt:package_test`.
SONiC's historical Azure FIPS-activation tests remain a separate gap: the old
pipeline disables that step or applies its existing known-issue exclusions.
This target does not activate `/etc/fips/fips_enable`, claim those tests passed,
or establish FIPS certification. Final container/guest configuration needs its
own integration validation.

The suite extracts its plugin inputs directly from the SymCrypt runtime TAR with
the declared BSD tar toolchain. It does not build or install Debian packages.
