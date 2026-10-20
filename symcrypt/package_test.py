"""Validate installed SymCrypt bytes, integrity enforcement, and OpenSSL consumers."""

import hashlib
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import tempfile

from elftools.elf.elffile import ELFFile
from openssl.package_test import build_id, check_gdb, check_symbols, run, unpack_files


def tamper_digest(source, destination):
    """Change only the expected integrity digest in a disposable ELF copy."""
    with source.open("rb") as stream:
        elf = ELFFile(stream)
        symbol = elf.get_section_by_name(".symtab").get_symbol_by_name("SymCryptVolatileFipsHmacDigest")[0]
        section = elf.get_section(symbol["st_shndx"])
        offset = section["sh_offset"] + symbol["st_value"] - section["sh_addr"]
    data = bytearray(source.read_bytes())
    data[offset] ^= 1
    destination.write_bytes(data)


def main():
    assert len(sys.argv) == 7
    runtime_tar, debug_tar, openssl_libs, openssl_commands, raw_core, unit_test = sys.argv[1:]
    triplet = {"x86_64": "x86_64-linux-gnu", "aarch64": "aarch64-linux-gnu"}[platform.machine()]
    with tempfile.TemporaryDirectory(dir=os.environ.get("TEST_TMPDIR")) as temporary:
        scratch = Path(temporary)
        root, symbols = scratch / "root", scratch / "symbols"
        entries = unpack_files(runtime_tar, root)
        debug_entries = unpack_files(debug_tar, symbols)
        unpack_files(openssl_libs, root)
        unpack_files(openssl_commands, root)
        for inventory, destination in [(entries, root), (debug_entries, symbols)]:
            for name, item in inventory.items():
                assert (item.uid, item.gid) == (0, 0), name
                if item.isfile() and inventory is entries:
                    expected_mode = 0o755 if name.startswith("usr/lib/") else 0o644
                    assert item.mode == expected_mode, (name, item.mode)
                if item.issym():
                    assert not item.linkname.startswith("/"), name
                    target = destination / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.symlink_to(item.linkname)
                    assert target.resolve().is_relative_to(destination.resolve()), name

        libdir = root / "usr/lib" / triplet
        installed_files = {f"usr/lib/{triplet}/" + name for name in [
            "libsymcrypt.so.103.13.0", "libsymcryptengine.so", "ossl-modules/symcryptprovider.so",
        ]} | {"usr/share/doc/symcrypt-openssl/" + name for name in ["SymCrypt-LICENSE.txt", "LICENSE", "jitterentropy-LICENSE.bsd"]}
        installed_links = {f"usr/lib/{triplet}/" + name for name in [
            "libsymcrypt.so.103", "libsymcrypt.so", "symcryptengine.so", "engines-3/symcryptengine.so",
        ]}
        assert {name for name, item in entries.items() if item.isfile()} == installed_files
        assert {name for name, item in entries.items() if item.issym()} == installed_links
        core = libdir / "libsymcrypt.so.103.13.0"
        assert core.read_bytes() == Path(raw_core).read_bytes(), "sealed core changed during packaging"
        assert (libdir / "libsymcrypt.so").resolve() == core
        assert (libdir / "engines-3/symcryptengine.so").resolve() == libdir / "libsymcryptengine.so"
        identifier = build_id(core)
        debug = symbols / "usr/lib/debug/.build-id" / identifier[:2] / (identifier[2:] + ".debug")
        assert debug.is_file() and build_id(debug) == identifier
        # Shared debug tree packaging uses the paired ELF executable mode.
        assert debug_entries[str(debug.relative_to(symbols))].mode == 0o755
        assert ".debug_info" in run("readelf", "-SW", str(debug))
        sections = run("readelf", "-SW", str(core))
        assert ".debug_info" not in sections and ".gnu_debuglink" not in sections
        check_gdb(core, symbols, "SymCryptModuleMain", "modules/posix/common/module.c")
        expected_debug = {str(debug.relative_to(symbols))}
        for binary in [libdir / "libsymcryptengine.so", libdir / "ossl-modules/symcryptprovider.so"]:
            check_symbols(binary, symbols, scratch)
            identifier = build_id(binary)
            name = f"usr/lib/debug/.build-id/{identifier[:2]}/{identifier[2:]}.debug"
            expected_debug.add(name)
            # The shared deployment rule retains the paired binary's mode.
            assert debug_entries[name].mode == 0o755
        assert {name for name, item in debug_entries.items() if item.isfile()} == expected_debug

        environment = dict(os.environ, LD_LIBRARY_PATH=str(libdir), OPENSSL_CONF="/dev/null",
                           OPENSSL_MODULES=str(libdir / "ossl-modules"), OPENSSL_ENGINES=str(libdir / "engines-3"))
        # Loading invokes upstream's constructor: integrity, RNG, and algorithm
        # self-tests remain enabled. Disable core dumps only in the child test.
        loader = "import ctypes,resource,sys; resource.setrlimit(resource.RLIMIT_CORE,(0,0)); ctypes.CDLL(sys.argv[1])"
        run(sys.executable, "-c", loader, str(core), env=environment)
        altered = scratch / "altered.so"
        tamper_digest(core, altered)
        rejected = subprocess.run([sys.executable, "-c", loader, str(altered)], env=environment, capture_output=True)
        assert rejected.returncode == -signal.SIGSEGV, rejected
        openssl = root / "usr/bin/openssl"
        providers = run(str(openssl), "list", "-providers", "-provider", "symcryptprovider", env=environment)
        assert "symcryptprovider" in providers and "active" in providers, providers
        digest = run(str(openssl), "dgst", "-provider", "symcryptprovider", "-propquery", "provider=symcryptprovider",
                     "-sha256", input="abc", env=environment)
        assert hashlib.sha256(b"abc").hexdigest() in digest, digest
        # The engine ID is "symcrypt", while the installed file is named
        # symcryptengine.so. Explicit dynamic loading supplies both identities.
        engine = run(str(openssl), "engine", "dynamic", "-pre", "SO_PATH:" + str(libdir / "engines-3/symcryptengine.so"),
                     "-pre", "ID:symcrypt", "-pre", "LIST_ADD:1", "-pre", "LOAD", "-t", "-c", env=environment)
        assert "SCOSSL" in engine and "[ available ]" in engine, engine
        engine_digest = run(str(openssl), "dgst", "-engine", str(libdir / "engines-3/symcryptengine.so"),
                            "-sha256", input="abc", env=environment)
        assert "Engine " in engine_digest and hashlib.sha256(b"abc").hexdigest() in engine_digest, engine_digest
        # Native Make runs this same full upstream test executable.
        print(run(str(Path(unit_test).resolve()), env=environment))
        print("Installed SymCrypt: unchanged sealed core, integrity rejection, original tests, symbols, provider and engine digests passed")


if __name__ == "__main__":
    main()
