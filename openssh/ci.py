#!/usr/bin/env python3
"""Build the native SONiC OpenSSH clients and retain their test evidence."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

from tools.bazel.ci import audit, command, retain_resolution

TARGETS = ["//openssh:openssh_client_pkg", "//openssh:openssh_client_pkg.debug_symbols"]
GENERATED = {"notice": "AUTO-GENERATED. DO NOT EDIT MANUALLY.", "generator": "openssh/ci.py"}


def write_json(path, value):
    path.write_text(json.dumps({"_generated": GENERATED, **value}, indent=2) + "\n")


def retain_logs(output):
    """Keep the source commands and test logs, including failed configure actions."""
    # The same Bazel output symlink is used by the cquery package paths below.
    # Avoid a second configuration-less `bazel info` invocation: it cannot
    # resolve draft module overrides and root-repository platform aliases.
    base = Path("bazel-out").resolve()
    for component in ("openssh", "openssl"):
        for path in base.glob(f"*/bin/{component}/*_foreign_cc/*"):
            if path.is_file() and path.name in ("Configure.log", "build_script.sh", "wrapper_build_script.sh"):
                destination = output / "source-logs" / path.relative_to(base)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--architecture", choices=["amd64", "arm64"], required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--bazel-arg", action="append", default=[])
    args = parser.parse_args()
    machine = {"amd64": "x86_64", "arm64": "aarch64"}[args.architecture]
    if platform.machine() != machine:
        raise SystemExit(f"Native {machine} required; runner is {platform.machine()}")
    output = args.artifacts.resolve()
    output.mkdir(parents=True, exist_ok=True)
    flags = [f"--platforms=@sonic_build_infra//platforms:{machine}_trixie",
             f"--host_platform=@sonic_build_infra//platforms:{machine}_trixie",
             "--jobs=4", *args.bazel_arg]
    try:
        with (output / "actions.json").open("w") as stdout, (output / "audit.log").open("w") as stderr:
            subprocess.run(["bazel", "aquery", "deps(set(//openssh:package_test //openssh:upstream_tests_debug))",
                            *flags, "--include_file_write_contents", "--output=jsonproto"],
                           stdout=stdout, stderr=stderr, check=True)
        write_json(output / "audit.json", audit(json.loads((output / "actions.json").read_text())))
        retain_resolution(output, args.architecture, args.bazel_arg)
        # The original unit/compatibility targets and the private-agent smoke
        # execute in a separate no-cache action. CI starts with a fresh output
        # base, even when dependency builds are restored from the disk cache.
        command(["bazel", "build", "//openssh:upstream_tests_debug", *flags,
                 "--build_event_json_file=" + str(output / "upstream-events.json")],
                output / "upstream-test.log")
        test_tree = subprocess.check_output(["bazel", "cquery", "//openssh:upstream_tests_debug", *flags, "--output=files"], text=True).strip()
        smoke = json.loads((Path(test_tree) / "client-smoke.json").read_text())
        if smoke.get("status") != "passed" or smoke.get("config_cipher_key_and_private_agent") != "passed":
            raise SystemExit("Missing successful private-client smoke receipt")
        write_json(output / "client-smoke.json", smoke)
        command(["bazel", "test", "//openssh:package_test", *flags, "--test_output=errors",
                 "--nocache_test_results", "--build_event_json_file=" + str(output / "package-events.json")],
                output / "package-test.log")
        packages = []
        for target in TARGETS:
            files = subprocess.check_output(["bazel", "cquery", target, *flags, "--output=files"], text=True).splitlines()
            if len(files) != 1:
                raise SystemExit(f"Expected one TAR from {target}: {files}")
            destination = output / (target.split(":")[1] + ".tar")
            shutil.copyfile(files[0], destination)
            packages.append({"target": target, "file": destination.name,
                             "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()})
        source = subprocess.check_output(["bazel", "cquery", "@openssh_src//:source.json", *flags, "--output=files"], text=True).strip()
        source_path = Path(source)
        if not source_path.is_file():
            source_path = Path("bazel-out").resolve().parent / source_path
        shutil.copyfile(source_path, output / "source.json")
        git = ["git", "-c", "safe.directory=" + str(Path.cwd())]
        checkout = subprocess.check_output([*git, "rev-parse", "HEAD"], text=True).strip()
        dirty = bool(subprocess.check_output([*git, "status", "--porcelain", "--untracked-files=no"], text=True).strip())
        write_json(output / "result.json", {
            "tested_commit": checkout, "pull_request_head": os.environ.get("CI_HEAD_SHA"),
            "working_tree_dirty": dirty, "machine": platform.machine(), "architecture": args.architecture,
            "packages": packages, "upstream_unit_and_compatibility_tests": "passed",
            "private_client_agent_smoke": "passed", "installed_package_test": "passed",
            "debug_pairs": 10,
            "scope": "OpenSSH clients; no server, network SSH, provider certification or final image validation",
        })
    finally:
        retain_logs(output)


if __name__ == "__main__":
    main()
