"""Check the Debian client runtime contract and every matching symbol file."""

import os
from pathlib import Path
import platform
import struct
import sys
import tempfile

from openssl.package_test import check_gdb, check_symbols, unpack_files


def runtime_manifest(path):
    files, binaries = set(), set()
    for line in path.read_text().splitlines():
        words = line.strip().split()
        if not words or words[0].startswith("#"):
            continue
        if len(words) == 1:
            destination = words[0]
            if destination.startswith(("usr/bin/", "usr/lib/openssh/")):
                binaries.add(destination)
        elif len(words) == 2:
            destination = words[1] + "/" + Path(words[0]).name
        elif len(words) == 3 and words[1] == "=>":
            destination = words[2]
        else:
            raise AssertionError("Unexpected Debian install directive: " + line)
        if "/man/" not in destination:
            files.add(destination)
    files.update({
        "usr/share/doc/openssh-client/copyright",
        # dh_installtmpfiles installs this source file separately from .install.
        # Include it directly so OCI consumers need no Debian helper execution.
        "usr/lib/tmpfiles.d/openssh-client.conf",
    })
    return files, binaries


def main():
    assert len(sys.argv) == 4
    expected_files, expected_binaries = runtime_manifest(Path(sys.argv[3]))
    machine = {"x86_64": 62, "aarch64": 183}[platform.machine()]
    with tempfile.TemporaryDirectory(dir=os.environ.get("TEST_TMPDIR")) as temporary:
        scratch = Path(temporary)
        root, symbols = scratch / "root", scratch / "symbols"
        entries = unpack_files(sys.argv[1], root)
        debug_entries = unpack_files(sys.argv[2], symbols)
        actual_files = {name for name, member in entries.items() if member.isfile()}
        assert actual_files == expected_files, (actual_files ^ expected_files)
        assert all(member.uid == member.gid == 0 for member in entries.values())
        binaries = {name for name in actual_files if (root / name).read_bytes().startswith(b"\x7fELF")}
        assert binaries == expected_binaries and len(binaries) == 10
        for name in sorted(binaries):
            binary = root / name
            header = binary.read_bytes()[:20]
            assert header[:6] == b"\x7fELF\x02\x01", name
            assert struct.unpack_from("<HH", header, 16) == (3, machine), name
            expected_mode = 0o4755 if name.endswith("/ssh-keysign") else 0o755
            assert entries[name].mode == expected_mode, (name, entries[name].mode)
            check_symbols(binary, symbols, scratch)
        debug_files = [name for name, member in debug_entries.items() if member.isfile()]
        assert len(debug_files) == 10 and all(name.endswith(".debug") for name in debug_files)
        assert entries["etc/ssh/ssh_config.d"].isdir()
        link = entries["usr/lib/systemd/user/graphical-session-pre.target.wants/ssh-agent.service"]
        assert link.issym() and link.linkname == "../ssh-agent.service"
        assert "$OpenBSD:" not in (root / "etc/ssh/ssh_config").read_text()
        tmpfiles = "usr/lib/tmpfiles.d/openssh-client.conf"
        assert entries[tmpfiles].mode == 0o644
        assert (root / tmpfiles).read_text().strip() == "x /tmp/ssh-*"
        check_gdb(root / "usr/bin/ssh", symbols, "main", "ssh.c")
        check_gdb(root / "usr/bin/ssh-keygen", symbols, "main", "ssh-keygen.c")
        print("OpenSSH client runtime manifest, native PIE, ownership and ten debug pairs passed")


if __name__ == "__main__":
    main()
