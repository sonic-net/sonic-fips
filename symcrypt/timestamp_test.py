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
               SYMCRYPT_COMMIT_HASH="53be637dab201a4c9d95e1cf58040c85d71cf3c2",
               SYMCRYPT_COMMIT_TIMESTAMP="2025-01-28T00:44:15Z",
               SOURCE_DATE_EPOCH=epoch)
    result = subprocess.run([sys.executable, str(destination / "scripts/version.py"),
                             "--build-info"], env=env, capture_output=True, text=True)
    return result, destination / "inc"


def main():
    source = Path(sys.argv[1]).resolve().parent.parent
    with tempfile.TemporaryDirectory(dir=os.environ.get("TEST_TMPDIR")) as temporary:
        root = Path(temporary)
        first, a = generate(source, root / "short", "UTC0", "1738025055")
        second, b = generate(source, root / "different-length-source-root", "EST5EDT", "1738025055")
        assert first.returncode == second.returncode == 0, (first, second)
        for header in ["buildInfo.h", "symcrypt_internal_shared.inc"]:
            assert (a / header).read_bytes() == (b / header).read_bytes(), header
        assert '2025-01-28T00:44:15+00:00' in (a / "buildInfo.h").read_text()
        changed, c = generate(source, root / "changed", "UTC0", "1738025056")
        assert changed.returncode == 0, changed
        assert '2025-01-28T00:44:16+00:00' in (c / "buildInfo.h").read_text()
        assert (a / "buildInfo.h").read_bytes() != (c / "buildInfo.h").read_bytes()
        assert (a / "symcrypt_internal_shared.inc").read_bytes() == (c / "symcrypt_internal_shared.inc").read_bytes()
        invalid, _ = generate(source, root / "invalid", "UTC0", "not-an-epoch")
        assert invalid.returncode != 0, invalid
    print("Upstream headers are identical across roots/timezones; epoch edits invalidate only build metadata")


if __name__ == "__main__":
    main()
