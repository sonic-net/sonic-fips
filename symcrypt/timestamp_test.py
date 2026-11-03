"""Exercise the real upstream version generator with declared build metadata."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def generate(source, destination, timezone, epoch):
    for name in [
        "scripts/version.py", "scripts/devops_utils.py", "version.json",
        "conf/buildInfo.h.in", "conf/symcrypt_internal_shared.inc.in",
    ]:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
    (destination / "inc").mkdir()
    env = dict(os.environ, TZ=timezone, PYTHONPATH=str(destination / "scripts"), SYMCRYPT_BRANCH="HEAD",
               SYMCRYPT_COMMIT_HASH="286762b7730e2b780678f5ab11fef2b1bad639e0",
               SYMCRYPT_COMMIT_TIMESTAMP="2026-08-05T21:48:57Z",
               SOURCE_DATE_EPOCH=epoch)
    result = subprocess.run([sys.executable, str(destination / "scripts/version.py"),
                             "--build-info"], env=env, capture_output=True, text=True)
    return result, destination / "inc"


def main():
    source = Path(sys.argv[1]).resolve().parent.parent
    with tempfile.TemporaryDirectory(dir=os.environ.get("TEST_TMPDIR")) as temporary:
        root = Path(temporary)
        first, a = generate(source, root / "short", "UTC0", "1785966537")
        second, b = generate(source, root / "different-length-source-root", "EST5EDT", "1785966537")
        assert first.returncode == second.returncode == 0, (first, second)
        for header in ["buildInfo.h", "symcrypt_internal_shared.inc"]:
            assert (a / header).read_bytes() == (b / header).read_bytes(), header
        assert '2026-08-05T21:48:57+00:00' in (a / "buildInfo.h").read_text()
        changed, c = generate(source, root / "changed", "UTC0", "1785966538")
        assert changed.returncode == 0, changed
        assert '2026-08-05T21:48:58+00:00' in (c / "buildInfo.h").read_text()
        assert (a / "buildInfo.h").read_bytes() != (c / "buildInfo.h").read_bytes()
        assert (a / "symcrypt_internal_shared.inc").read_bytes() == (c / "symcrypt_internal_shared.inc").read_bytes()
        invalid, _ = generate(source, root / "invalid", "UTC0", "not-an-epoch")
        assert invalid.returncode != 0, invalid
    print("Upstream headers are identical across roots/timezones; epoch edits invalidate only build metadata")


if __name__ == "__main__":
    main()
