#!/usr/bin/env python3
"""Audit, test and retain the installed SymCrypt runtime/debug TARs."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

from ci import audit, command, retain_resolution


PACKAGES = ["runtime", "runtime.debug_symbols"]
BUILD_EVIDENCE = ["compile_commands.json", "CMakeCache.txt", "CMake.log",
                  "provider_compile_commands.json", "provider_CMakeCache.txt"]
ARTIFACT_TARGETS = (["//symcrypt:" + name for name in PACKAGES]
                    + ["//symcrypt:packaged_" + name for name in BUILD_EVIDENCE])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--architecture", choices=["amd64", "arm64"], required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--bazel-arg", action="append", default=[])
    args = parser.parse_args()
    machine = {"amd64": "x86_64", "arm64": "aarch64"}[args.architecture]
    assert platform.machine() == machine, "native execution is required"
    output = args.artifacts.resolve()
    output.mkdir(parents=True, exist_ok=True)
    flags = [f"--platforms=@sonic_build_infra//platforms:{machine}_trixie",
             f"--host_platform=@sonic_build_infra//platforms:{machine}_trixie", "--jobs=4", *args.bazel_arg]
    with (output / "actions.json").open("w") as stdout, (output / "audit.log").open("w") as stderr:
        query = "deps(set(//symcrypt:package_test " + " ".join(ARTIFACT_TARGETS) + "))"
        subprocess.run(["bazel", "aquery", query, *flags,
                        "--include_file_write_contents", "--output=jsonproto"], stdout=stdout, stderr=stderr, check=True)
    (output / "audit.json").write_text(json.dumps(audit(json.loads((output / "actions.json").read_text())), indent=2) + "\n")
    # Also analyze the real public package test from a downstream module. This
    # catches extensions that work only when sonic-fips is the workspace root.
    consumer = Path("symcrypt/tests/consumer")
    with (output / "consumer-actions.json").open("w") as stdout, (output / "consumer-audit.log").open("w") as stderr:
        subprocess.run(["bazel", "--output_base=" + str(output.parent / (output.name + "-consumer-bazel")),
                        "aquery", "deps(@sonic_fips//symcrypt:package_test)", *flags,
                        "--include_file_write_contents", "--output=jsonproto"],
                       cwd=consumer, stdout=stdout, stderr=stderr, check=True)
    (output / "consumer-audit.json").write_text(json.dumps(audit(json.loads((output / "consumer-actions.json").read_text())), indent=2) + "\n")
    shutil.copyfile(consumer / "MODULE.bazel", output / "consumer.MODULE.bazel")
    shutil.copyfile(consumer / "MODULE.bazel.lock", output / "consumer.MODULE.bazel.lock")
    retain_resolution(output, args.architecture, args.bazel_arg)
    command(["bazel", "test", "//symcrypt:package_test", *flags, "--test_output=errors", "--nocache_test_results",
             "--build_event_json_file=" + str(output / "events.json")], output / "test.log")
    # cquery reports configured paths without building them. Evidence outputs
    # are not all dependencies of package_test, so materialize them explicitly.
    command(["bazel", "build", *ARTIFACT_TARGETS, *flags], output / "artifact-build.log")
    packages = []
    for target in PACKAGES:
        files = subprocess.check_output(["bazel", "cquery", "//symcrypt:" + target, *flags, "--output=files"], text=True).splitlines()
        assert len(files) == 1, files
        destination = output / (target + ".tar")
        shutil.copyfile(files[0], destination)
        packages.append({"target": "//symcrypt:" + target, "file": destination.name,
                         "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()})
    evidence = output / "core-build"
    evidence.mkdir(exist_ok=True)
    for target in BUILD_EVIDENCE:
        files = subprocess.check_output(["bazel", "cquery", "//symcrypt:packaged_" + target, *flags, "--output=files"], text=True).splitlines()
        for source in files:
            shutil.copyfile(source, evidence / Path(source).name)
    cache = (evidence / "CMakeCache.txt").read_text()
    assert "Clang" in (evidence / "CMake.log").read_text()
    assert "--ld-path=" in cache and f"{machine}-linux-gnu-ld" in cache
    assert "SYMCRYPT_FIPS_BUILD:BOOL=ON" in cache and "SYMCRYPT_FIPS_POSTPROCESS:BOOL=ON" in cache
    commands = json.loads((evidence / "compile_commands.json").read_text())
    assert commands and all("symcrypt_llvm/bin/cc_wrapper.sh" in item["command"] for item in commands)
    assert all("--sysroot=" in item["command"] for item in commands)
    language_commands = [item for item in commands if item["file"].endswith((".c", ".cpp"))]
    assert language_commands and all("-resource-dir" in item["command"] for item in language_commands)
    # Clang's C headers come from its declared resource directory and sysroot;
    # C++ also disables its default C++ search and selects sysroot libstdc++.
    cpp_commands = [item for item in commands if item["file"].endswith(".cpp")]
    assert cpp_commands and all("-nostdinc++" in item["command"] for item in cpp_commands)
    assert not any(" -I/usr/" in item["command"] or " -isystem /usr/" in item["command"] for item in commands)
    provider_commands = json.loads((evidence / "provider_compile_commands.json").read_text())
    assert provider_commands and all("gcc-14.2.0-linux-target-" in item["command"] for item in provider_commands)
    assert not any(" -I/usr/" in item["command"] or " -isystem /usr/" in item["command"] for item in provider_commands)
    shutil.copytree("bazel-testlogs/symcrypt/package_test", output / "package-test", dirs_exist_ok=True)
    revision = subprocess.check_output(["git", "-c", "safe.directory=" + str(Path.cwd()), "rev-parse", "HEAD"], text=True).strip()
    (output / "result.json").write_text(json.dumps({
        "_generated": {"notice": "AUTO-GENERATED. DO NOT EDIT MANUALLY.", "generator": "tools/bazel/symcrypt_ci.py"},
        "tested_commit": revision, "pull_request_head": os.environ.get("CI_HEAD_SHA"),
        "architecture": args.architecture, "packages": packages,
        "installed_package_test": "passed", "certification_claim": False,
        "scope": "native core unit tests, sealed-byte preservation, integrity rejection, matching symbols, source OpenSSL provider and engine",
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
