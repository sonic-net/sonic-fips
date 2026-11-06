load("@rules_foreign_cc//foreign_cc:defs.bzl", "cmake")

PROVIDER_PLATFORMS = {
    "aarch64": "@symcrypt_openssl_src//:cmake-toolchain/LinuxUserMode-ARM64.cmake",
    "x86_64": "@symcrypt_openssl_src//:cmake-toolchain/LinuxUserMode-AMD64.cmake",
}

_PROVIDER_CACHE = {
    "CMAKE_BUILD_TYPE": "Release",
    # Installed consumers use their declared loader/library paths. Avoid
    # CMake build-RPATH padding that survives its install-time RPATH removal.
    "CMAKE_SKIP_RPATH": "ON",
    "CMAKE_EXPORT_COMPILE_COMMANDS": "ON",
    # Keep the declared GCC toolchain when the upstream ARM platform file runs.
    "SCOSSL_USE_DEFAULT_COMPILER": "ON",
    "CMAKE_INSTALL_LIBDIR": "lib",
    "CMAKE_INSTALL_INCLUDEDIR": "include",
    "OPENSSL_ENGINES": "lib",
    "OPENSSL_PROVIDERS": "lib",
    "OPENSSL_INCLUDE_DIR": "$$EXT_BUILD_DEPS$$/build/usr/include",
    "SYMCRYPT_ROOT_DIR": "$$EXT_BUILD_DEPS$$/symcrypt",
    "SYMCRYPT_LIBRARY": "$$EXT_BUILD_DEPS$$/symcrypt/lib/libsymcrypt.so",
    # GNU ld must also find libcrypto's declared compression dependencies when
    # linking the native SslPlay executable. This is a build-only search path.
    "CMAKE_EXE_LINKER_FLAGS": "-Wl,-rpath-link,$$EXT_BUILD_DEPS$$/lib",
}

def symcrypt_provider(name, testonly = False, uncached = False):
    """Build the actual upstream provider/engine with one shared contract."""

    # Native Make leaves this component on GCC; only the core dependency selects
    # Clang. The unchanged upstream platform file supplies its CPU definitions.
    cmake(
        name = name,
        testonly = testonly,
        tags = ["no-cache"] if uncached else [],
        build_args = ["-j4"],
        build_data = select({
            "@platforms//cpu:" + cpu: [platform]
            for cpu, platform in PROVIDER_PLATFORMS.items()
        }),
        cache_entries = select({
            "@platforms//cpu:" + cpu: _PROVIDER_CACHE | {
                # The target CPU file appends flags after CMake initializes them.
                "CMAKE_PROJECT_SymCrypt-OpenSSL_INCLUDE": "$(execpath {})".format(PROVIDER_PLATFORMS[cpu]),
                "OPENSSL_CRYPTO_LIBRARY": "$$EXT_BUILD_DEPS$$/build/usr/lib/" + triplet + "/libcrypto.so.3",
                "OPENSSL_SSL_LIBRARY": "$$EXT_BUILD_DEPS$$/build/usr/lib/" + triplet + "/libssl.so.3",
            }
            for cpu, triplet in [
                ("x86_64", "x86_64-linux-gnu"),
                ("aarch64", "aarch64-linux-gnu"),
            ]
        }),
        configuration = "Release",
        features = ["-sanitize_pwd"],
        lib_name = "symcrypt_openssl",
        lib_source = "@symcrypt_openssl_src//:sources",
        out_binaries = ["SslPlay"],
        out_data_files = [
            "evidence/provider_compile_commands.json",
            "evidence/provider_CMakeCache.txt",
        ],
        out_shared_libs = [
            "symcryptengine.so",
            "symcryptprovider.so",
        ],
        postfix_script = """mkdir -p "$$INSTALLDIR/bin" "$$INSTALLDIR/evidence"
cp "$$BUILD_TMPDIR/test/SslPlay/SslPlay" "$$INSTALLDIR/bin/SslPlay"
cp "$$BUILD_TMPDIR/compile_commands.json" "$$INSTALLDIR/evidence/provider_compile_commands.json"
cp "$$BUILD_TMPDIR/CMakeCache.txt" "$$INSTALLDIR/evidence/provider_CMakeCache.txt"
""",
        set_file_prefix_map = True,
        # rules_foreign_cc stages a foreign dependency's install tree, so list its
        # non-foreign DSO dependencies explicitly for the link-only directory too.
        deps = [
            ":core",
            "//openssl:build",
            "@openssl_deps//libzstd-dev:libzstd",
            "@openssl_deps//zlib1g-dev:zlib1g",
        ],
    )
