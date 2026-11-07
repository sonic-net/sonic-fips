"""Exercise upstream OpenSSH's real OpenSSL selection and mismatch check."""

import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile

from openssl.package_test import unpack_files


def main():
    assert len(sys.argv) == 5
    source = Path(sys.argv[1]).resolve().parent
    tools = {name: shutil.which(name) for name in ("gcc", "autoconf", "autoheader")}
    assert all(tools.values()), "Native CI declares GCC14 and Autoconf"
    assert subprocess.check_output([tools["gcc"], "-dumpversion"], text=True).strip().split(".")[0] == "14"
    triplet = {"x86_64": "x86_64-linux-gnu", "aarch64": "aarch64-linux-gnu"}[platform.machine()]
    with tempfile.TemporaryDirectory(dir=os.environ.get("TEST_TMPDIR")) as temporary:
        root = Path(temporary)
        installed = root / "installed"
        links = {}
        for archive in sys.argv[2:]:
            links.update({name: entry.linkname for name, entry in unpack_files(archive, installed).items()
                          if entry.issym() and not Path(entry.linkname).is_absolute()})
        for name, target in links.items():
            path = installed / name
            assert (path.parent / target).resolve().is_relative_to(installed)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(target)
        # The adapter expects Autoconf in the declared build-tools layout.
        # Native CI supplies this fixture's loader; source builds use the
        # declared target runtime. Never export its libc into host tools.
        runtime = root / "runtime"
        (runtime / "bin").mkdir(parents=True)
        (runtime / "usr").mkdir()
        (runtime / "bin/autoconf").symlink_to(tools["autoconf"])
        (runtime / "usr/lib").mkdir()
        for library in Path("/usr/lib").glob("*/ld-linux-*.so.*"):
            (runtime / "usr/lib" / library.name).symlink_to(library)
        dependency = root / "deps"
        dependency.mkdir()
        (dependency / "build").symlink_to(installed, target_is_directory=True)
        prefix = installed / "usr"
        libraries = prefix / "lib" / triplet
        assert (libraries / "libcrypto.so").exists()
        assert (libraries / "libcrypto.so.3").is_file()
        bad = root / "mismatched-prefix"
        shutil.copytree(prefix / "include", bad / "include")
        (bad / "lib").symlink_to(prefix / "lib", target_is_directory=True)
        # Keep the actual source library unchanged. Alter only a private header
        # version as a negative control for upstream's existing strict check.
        header = bad / "include/openssl/opensslv.h"
        text = header.read_text()
        match = re.search(r"(#\s*define OPENSSL_VERSION_PATCH\s+)(\d+)", text)
        assert match and int(match.group(2)) > 0
        text = text[:match.start(2)] + str(int(match.group(2)) - 1) + text[match.end(2):]
        header.write_text(text)
        records = []
        for negative in (False, True):
            work = root / ("negative" if negative else "positive")
            shutil.copytree(source, work)
            selected = bad if negative else prefix
            env = {
                **os.environ,
                "CC": tools["gcc"],
                "AUTOCONF": str(runtime / "bin/autoconf"),
                "EXT_BUILD_DEPS": str(dependency),
                "AUTOHEADER": tools["autoheader"],
                "CFLAGS": "-O2",
                # Simulate a transitive SDK appearing before the source SDK.
                # Upstream --with-ssl-dir must prepend the selected owner.
                "CPPFLAGS": "-I" + str(bad / "include") + " -I" + str(prefix / "include" / triplet),
                "LDFLAGS": "-L" + str(libraries) + " -Wl,-rpath-link=" + str(libraries) + " -Wl,-t",
                "OPENSSL_CONF": "/dev/null",
            }
            env.pop("LD_LIBRARY_PATH", None)
            command = [
                "/bin/sh", "bazel-configure", "--prefix=/usr",
                "--with-ssl-dir=" + str(selected), "--without-rpath",
                "--without-pam", "--without-selinux", "--without-libedit",
                "--without-kerberos5", "--without-security-key-builtin",
            ]
            completed = subprocess.run(command, cwd=work, env=env, capture_output=True, text=True)
            output = completed.stdout + completed.stderr
            log = (work / "config.log").read_text()
            if negative:
                assert completed.returncode != 0, output
                assert "Your OpenSSL headers do not match your" in output, output
                assert "checking whether OpenSSL's headers match the library... no" in output, output
            else:
                assert completed.returncode == 0, output
                assert "checking whether OpenSSL's headers match the library... yes" in output, output
                # Linker tracing establishes the selected library file, not
                # merely the runtime SONAME or an inferred header version.
                assert str(libraries / "libcrypto.so") in log, log
            records.append({
                "case": "mismatched-header-rejected" if negative else "source-header-and-library-selected",
                "status": "passed",
                "observed_checks": [line for line in output.splitlines()
                                    if "OpenSSL header version" in line or "OpenSSL library version" in line
                                    or "headers match the library" in line],
            })
        print(json.dumps({"architecture": platform.machine(), "checks": records}, indent=2))


if __name__ == "__main__":
    main()
