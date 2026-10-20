"""Check the four installed SONiC Kerberos packages and matching debug files."""

import os
from pathlib import Path
import platform
import re
import struct
import sys
import tempfile

from openssl.package_test import check_gdb, check_symbols, run, unpack_files

LIBRARIES = {
    "libk5crypto3": ("libk5crypto.so.3.1", "krb5_c_encrypt", "encrypt.c"),
    "libkrb5support0": ("libkrb5support.so.0.1", "k5_buf_init_dynamic", "k5buf.c"),
    "libkrb5-3": ("libkrb5.so.3.3", "krb5_init_context", "init_ctx.c"),
    "libgssapi-krb5-2": ("libgssapi_krb5.so.2.2", "gss_indicate_mechs", "g_initialize.c"),
}


def check_manifest(binary, manifest):
    # Debian marks strlcpy/strlcat compatibility exports optional when libc supplies them.
    expected = {line.split()[0] for line in Path(manifest).read_text().splitlines() if line.startswith(" ") and not line.lstrip().startswith("(optional)")}
    versions = {name.split("@", 1)[1] for name in expected}
    actual = set()
    for line in run("nm", "-D", "--defined-only", "--format=posix", str(binary)).splitlines():
        name = line.split()[0].replace("@@", "@")
        actual.add(name)
        if name in versions:
            actual.add(name + "@" + name)
    assert expected <= actual, sorted(expected - actual)
    return len(expected)


def main():
    assert len(sys.argv) == 18
    openssl_runtime = sys.argv[1]
    triplet, machine = {"x86_64": ("x86_64-linux-gnu", 62), "aarch64": ("aarch64-linux-gnu", 183)}[platform.machine()]
    with tempfile.TemporaryDirectory(dir=os.environ.get("TEST_TMPDIR")) as temporary:
        scratch = Path(temporary)
        root, symbols = scratch / "root", scratch / "symbols"
        prefix = "usr/lib/" + triplet + "/"
        symbol_count = 0
        for index in range(2, len(sys.argv), 4):
            package, runtime, debug_tar, manifest = sys.argv[index:index + 4]
            library, function, source = LIBRARIES[package]
            entries = unpack_files(runtime, root)
            debug_entries = unpack_files(debug_tar, symbols)
            elf_paths = [prefix + library]
            regular = {prefix + library, "usr/share/doc/" + package + "/copyright"}
            if package == "libkrb5-3":
                elf_paths.append(prefix + "krb5/plugins/preauth/spake.so")
                regular.update({elf_paths[-1], "usr/share/doc/libkrb5-3/README", "usr/share/doc/libkrb5-3/README.Debian"})
                assert entries[prefix + "krb5/plugins/libkrb5"].isdir()
            if package == "libgssapi-krb5-2":
                assert entries["etc/gss/mech.d"].isdir()
            assert {name for name, item in entries.items() if item.isfile()} == regular
            soname = library.rsplit(".", 1)[0]
            assert {name for name, item in entries.items() if item.issym()} == {prefix + soname}
            alias = entries[prefix + soname]
            assert alias.linkname == library
            (root / prefix / soname).symlink_to(library)
            assert all(item.uid == item.gid == 0 for item in entries.values())
            assert len([item for item in debug_entries.values() if item.isfile()]) == len(elf_paths)
            assert all(item.uid == item.gid == 0 for item in debug_entries.values())
            for path in elf_paths:
                assert entries[path].mode == 0o644
                binary = root / path
                header = binary.read_bytes()[:20]
                assert header[:6] == b"\x7fELF\x02\x01" and struct.unpack_from("<HH", header, 16) == (3, machine)
                dynamic = run("readelf", "-d", str(binary))
                assert not re.search(r"\((?:RPATH|RUNPATH)\)", dynamic), dynamic
                check_symbols(binary, symbols, scratch)
                if path.endswith("/spake.so"):
                    check_gdb(binary, symbols, "clpreauth_spake_initvt", "spake_client.c")
            binary = root / prefix / library
            dynamic = run("readelf", "-d", str(binary))
            assert re.search(r"SONAME.*\[" + re.escape(soname) + r"\]", dynamic), dynamic
            if package == "libk5crypto3":
                assert re.search(r"NEEDED.*\[libcrypto.so.3\]", dynamic), dynamic
            check_gdb(binary, symbols, function, source)
            symbol_count += check_manifest(binary, manifest)

        # Load the installed package combination with the source OpenSSL TAR.
        # Host libc/system libraries remain test prerequisites; image-level
        # validation checks the complete installed dependency set separately.
        unpack_files(openssl_runtime, root)
        libdir = root / prefix
        environment = dict(os.environ, LD_LIBRARY_PATH=str(libdir), OPENSSL_CONF="/dev/null", KRB5_CONFIG="/dev/null")
        probe = '''import ctypes, pathlib, sys
class Data(ctypes.Structure):
    _fields_=[("magic",ctypes.c_int32),("length",ctypes.c_uint),("data",ctypes.c_void_p)]
root=pathlib.Path(sys.argv[1])
libs=[ctypes.CDLL(str(root/name)) for name in ["libk5crypto.so.3", "libkrb5support.so.0", "libkrb5.so.3", "libgssapi_krb5.so.2", "krb5/plugins/preauth/spake.so"]]
lib=libs[0]
lib.krb5_c_random_make_octets.argtypes=[ctypes.c_void_p,ctypes.POINTER(Data)]
lib.krb5_c_random_make_octets.restype=ctypes.c_int32
value=ctypes.create_string_buffer(32)
data=Data(0,32,ctypes.addressof(value))
assert lib.krb5_c_random_make_octets(None,ctypes.byref(data)) == 0
assert value.raw[:32] != bytes(32)
context=ctypes.c_void_p()
libs[2].krb5_init_context.argtypes=[ctypes.POINTER(ctypes.c_void_p)]
libs[2].krb5_init_context.restype=ctypes.c_int32
assert libs[2].krb5_init_context(ctypes.byref(context)) == 0
libs[2].krb5_free_context.argtypes=[ctypes.c_void_p]
libs[2].krb5_free_context(context)
minor=ctypes.c_uint32()
mechanisms=ctypes.c_void_p()
libs[3].gss_indicate_mechs.argtypes=[ctypes.POINTER(ctypes.c_uint32),ctypes.POINTER(ctypes.c_void_p)]
libs[3].gss_indicate_mechs.restype=ctypes.c_uint32
assert libs[3].gss_indicate_mechs(ctypes.byref(minor),ctypes.byref(mechanisms)) == 0
libs[3].gss_release_oid_set.argtypes=[ctypes.POINTER(ctypes.c_uint32),ctypes.POINTER(ctypes.c_void_p)]
assert libs[3].gss_release_oid_set(ctypes.byref(minor),ctypes.byref(mechanisms)) == 0
mapped=pathlib.Path("/proc/self/maps").read_text()
assert str(root/"libcrypto.so.3") in mapped
'''
        run(sys.executable, "-c", probe, str(libdir), env=environment)
        print(f"Installed Kerberos: four packages, five ELF/debug pairs, {symbol_count} Debian versioned symbols, random/context/GSS APIs and source OpenSSL loading passed")


if __name__ == "__main__":
    main()
