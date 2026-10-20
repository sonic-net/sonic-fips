"""Retain the original OpenSSL test harness result with source-built plugins."""

import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys


def main():
    source = Path(sys.argv[1])
    log = source.read_text()
    summaries = re.findall(r"Files=(\d+), Tests=(\d+),", log)
    outcomes = re.findall(r"^Result: (PASS|FAIL)\s*$", log, re.MULTILINE)
    assert outcomes and outcomes[-1] == "PASS" and summaries, log[-6000:]
    files, tests = map(int, summaries[-1])
    assert files > 0 and tests > 0
    output = Path(os.environ["TEST_UNDECLARED_OUTPUTS_DIR"])
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, output / "openssl-suite.log")
    (output / "openssl-suite.json").write_text(json.dumps({
        "_generated": {"notice": "AUTO-GENERATED. DO NOT EDIT MANUALLY.", "generator": "openssl/integration/suite_test.py"},
        "status": "passed", "architecture": platform.machine(),
        "recipe_files": files, "tests": tests,
        "scope": "Original vendor test suite with declared source-built SymCrypt plugins; no host FIPS mode change or certification claim.",
        "log_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }, indent=2) + "\n")
    print(f"OpenSSL vendor suite passed: {files} recipes, {tests} tests")


if __name__ == "__main__":
    main()
