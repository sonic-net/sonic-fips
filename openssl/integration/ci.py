#!/usr/bin/env python3
"""Run the original OpenSSL test suite with source-built SymCrypt prerequisites."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

from tools.bazel.ci import audit, command, retain_resolution

TARGET = "//openssl/integration:openssl_symcrypt_test"
RUNTIME = "//symcrypt:runtime"
GENERATED = {"notice": "AUTO-GENERATED. DO NOT EDIT MANUALLY.", "generator": "openssl/integration/ci.py"}


def write_json(path, value):
    path.write_text(json.dumps({"_generated": GENERATED, **value}, indent=2) + "\n")


def retain_logs(output):
    base = Path("bazel-out").resolve()
    for component in ("openssl", "openssl/integration", "symcrypt"):
        for path in base.glob(f"*/bin/{component}/*_foreign_cc/*"):
            if path.is_file() and path.name in ("Configure.log", "CMake.log", "build_script.sh", "wrapper_build_script.sh"):
                destination = output / "source-logs" / path.relative_to(base)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)
    logs = Path("bazel-testlogs/openssl/integration/openssl_symcrypt_test")
    for name in ("test.log", "test.xml", "test.outputs/openssl-suite.json", "test.outputs/openssl-suite.log"):
        path = logs / name
        if path.is_file():
            shutil.copyfile(path, output / path.name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--architecture", choices=["amd64", "arm64"], required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--bazel-arg", action="append", default=[])
    args = parser.parse_args()
    machine = {"amd64": "x86_64", "arm64": "aarch64"}[args.architecture]
    if platform.machine() != machine:
        raise SystemExit(f"Native {machine} required; runner is {platform.machine()}")
    if Path("/etc/fips/fips_enable").exists():
        raise SystemExit("Run this ordinary-mode suite in a fresh container without host FIPS activation")
    output = args.artifacts.resolve()
    output.mkdir(parents=True, exist_ok=True)
    flags = [f"--platforms=@sonic_build_infra//platforms:{machine}_trixie",
             f"--host_platform=@sonic_build_infra//platforms:{machine}_trixie",
             "--jobs=4", *args.bazel_arg]
    try:
        with (output / "actions.json").open("w") as stdout, (output / "audit.log").open("w") as stderr:
            subprocess.run(["bazel", "aquery", f"deps(set({TARGET} {RUNTIME}))", *flags,
                            "--include_file_write_contents", "--output=jsonproto"], stdout=stdout, stderr=stderr, check=True)
        write_json(output / "audit.json", audit(json.loads((output / "actions.json").read_text())))
        retain_resolution(output, args.architecture, args.bazel_arg)
        command(["bazel", "test", TARGET, *flags, "--nocache_test_results",
                 "--nozip_undeclared_test_outputs", "--test_output=errors",
                 "--build_event_json_file=" + str(output / "events.json")], output / "build-and-test.log")
        retain_logs(output)
        summary = json.loads((output / "openssl-suite.json").read_text())
        if summary.get("status") != "passed" or summary.get("architecture") != machine:
            raise SystemExit("Missing successful native vendor-suite receipt")
        # The plugin inputs come from the runtime TAR. Build that declared
        # artifact explicitly before cquery locates it for evidence retention.
        command(["bazel", "build", RUNTIME, *flags], output / "runtime-build.log")
        archive = subprocess.check_output(["bazel", "cquery", RUNTIME, *flags, "--output=files"], text=True).strip()
        shutil.copyfile(archive, output / "symcrypt-runtime.tar")
        git = ["git", "-c", "safe.directory=" + str(Path.cwd())]
        write_json(output / "result.json", {
            "tested_commit": subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip(),
            "pull_request_head": os.environ.get("CI_HEAD_SHA"),
            "working_tree_dirty": bool(subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip()),
            "machine": platform.machine(), "architecture": args.architecture,
            "original_vendor_suite": "passed", "recipe_files": summary["recipe_files"], "tests": summary["tests"],
            "symcrypt_runtime_sha256": hashlib.sha256((output / "symcrypt-runtime.tar").read_bytes()).hexdigest(),
            "scope": "Ordinary-mode vendor suite with source-built plugins available; host FIPS activation and certification are not tested",
        })
    finally:
        retain_logs(output)


if __name__ == "__main__":
    main()
