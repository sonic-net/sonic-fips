#!/usr/bin/env python3
"""Build OpenSSL's runtime/debug packages and retain native CI evidence."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess


TARGETS = [
    "//openssl:libssl3t64_pkg",
    "//openssl:openssl_pkg",
    "//openssl:libssl3t64_pkg.debug_symbols",
    "//openssl:openssl_pkg.debug_symbols",
    "//openssl:libssl_dev_pkg",
]


def command(args, log):
    with log.open("w") as output:
        result = subprocess.run(args, stdout=output, stderr=subprocess.STDOUT)
    if result.returncode:
        raise SystemExit(f"Command failed ({result.returncode}); see {log}")


def retain_runtime_metadata(output, component, flags):
    """Build the package inventory from the same configured runtime TARs."""
    target = "//" + component + ":runtime_packages.json"
    command(["bazel", "build", target, *flags], output / "metadata-build.log")
    files = subprocess.check_output(["bazel", "cquery", target, *flags, "--output=files"], text=True).splitlines()
    if len(files) != 1:
        raise SystemExit(f"Expected one generated metadata file from {target}: {files}")
    destination = output / "runtime_packages.json"
    shutil.copyfile(files[0], destination)
    document = json.loads(destination.read_text())
    if document.get("schema") != 1 or document.get("module") != "sonic-fips" or not document.get("packages"):
        raise SystemExit("Generated package metadata lacks its source owner and packages")
    return {"target": target, "file": destination.name,
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()}


def retain_resolution(output, architecture, bazel_args):
    command(["bazel", "mod", "graph", "--lockfile_mode=update", *bazel_args],
            output / "module-graph.txt")
    shutil.copyfile("MODULE.bazel.lock", output / "MODULE.bazel.lock")
    inputs = {}
    for name in ["MODULE.bazel", ".bazelrc", ".bazelversion"]:
        destination = output / name
        shutil.copyfile(name, destination)
        inputs[name] = hashlib.sha256(destination.read_bytes()).hexdigest()
    generated = {name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                 for name in ["MODULE.bazel.lock", "module-graph.txt"]}
    (output / "resolution.json").write_text(json.dumps({
        "tested_commit": subprocess.check_output(
            ["git", "-c", "safe.directory=" + str(Path.cwd()), "rev-parse", "HEAD"],
            text=True).strip(),
        "pull_request_head": os.environ.get("CI_HEAD_SHA"),
        "architecture": architecture,
        "machine": platform.machine(),
        "bazel_args": bazel_args,
        "declared_inputs_sha256": inputs,
        "generated_evidence_sha256": generated,
    }, indent=2) + "\n")


def artifact_paths(graph):
    fragments = {item["id"]: item for item in graph["pathFragments"]}

    def path(key):
        item = fragments[key]
        parent = path(item["parentId"]) + "/" if item.get("parentId") else ""
        return parent + item["label"]

    return {item["id"]: path(item["pathFragmentId"]) for item in graph["artifacts"]}


def write_action_graph(bazel, expression, flags, output, log, cwd=None):
    def query(selector, *options):
        return json.loads(subprocess.check_output(
            [*bazel, "aquery", selector, *flags, "--output=jsonproto", *options], cwd=cwd, stderr=log,
        ))

    # Bazel 8.5.1 reads generated symlink targets when expanding runfiles
    # manifests. Keep their actions in the graph without reading unbuilt paths.
    graph = query(expression, "--noinclude_file_write_contents")
    with_contents = query(f'mnemonic("^(?!SourceSymlinkManifest$).*", {expression})',
                          "--include_file_write_contents", "--noinclude_commandline")
    # IDs are local to each query. A shared action can occur under multiple
    # owners. Attach its bytes to each record with the same key and output.
    content_paths = artifact_paths(with_contents)
    contents = {(action["actionKey"], content_paths[action["primaryOutputId"]]): action["fileContents"]
                for action in with_contents["actions"] if "fileContents" in action}
    paths = artifact_paths(graph)
    for action in graph["actions"]:
        key = (action.get("actionKey"), paths[action["primaryOutputId"]])
        if key in contents:
            action["fileContents"] = contents[key]
    json.dump(graph, output)


def audit(graph):
    artifacts = artifact_paths(graph)
    for action in graph["actions"]:
        outputs = [artifacts[key] for key in action.get("outputIds", [])]
        text = " ".join(action.get("arguments", [])) + "\n" + action.get("fileContents", "")
        if any(name.endswith(".deb") for name in outputs) or "dpkg-buildpackage" in text:
            raise SystemExit(f"Unexpected Debian package production: {outputs}")
        if re.search(r"dpkg-deb\b[^\n]*(?:--build|\s-b\b)", text):
            raise SystemExit(f"Unexpected dpkg-deb build: {outputs}")
    return {"actions": len(graph["actions"]), "deb_production": False}


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
    flags = [
        f"--platforms=@sonic_build_infra//platforms:{machine}_trixie",
        f"--host_platform=@sonic_build_infra//platforms:{machine}_trixie",
        "--jobs=4",
        *args.bazel_arg,
    ]
    tests = ["//openssl:package_test"]
    if args.architecture == "amd64":
        tests.append("//openssl:build_info_test")
    with (output / "actions.json").open("w") as stdout, (output / "audit.log").open("w") as stderr:
        write_action_graph(["bazel"], "deps(set(" + " ".join(tests + ["//openssl:runtime_packages.json"]) + "))",
                           flags, stdout, stderr)
    report = audit(json.loads((output / "actions.json").read_text()))
    (output / "audit.json").write_text(json.dumps(report, indent=2) + "\n")
    retain_resolution(output, args.architecture, args.bazel_arg)
    command(["bazel", "test", *tests, *flags, "--test_output=errors",
             "--nocache_test_results", "--build_event_json_file=" + str(output / "events.json")],
            output / "test.log")
    metadata = retain_runtime_metadata(output, "openssl", flags)
    packages = []
    for target in TARGETS:
        files = subprocess.check_output(["bazel", "cquery", target, *flags, "--output=files"], text=True).splitlines()
        if len(files) != 1:
            raise SystemExit(f"Expected one TAR from {target}: {files}")
        destination = output / (target.split(":")[1] + ".tar")
        shutil.copyfile(files[0], destination)
        packages.append({"target": target, "file": destination.name,
                         "sha256": hashlib.sha256(destination.read_bytes()).hexdigest()})
    checkout = subprocess.check_output(["git", "-c", "safe.directory=" + str(Path.cwd()),
                                        "rev-parse", "HEAD"], text=True).strip()
    dirty = bool(subprocess.check_output(["git", "-c", "safe.directory=" + str(Path.cwd()),
                                          "status", "--porcelain"], text=True).strip())
    (output / "result.json").write_text(json.dumps({
        "tested_commit": checkout,
        "pull_request_head": os.environ.get("CI_HEAD_SHA"),
        "working_tree_dirty": dirty,
        "machine": platform.machine(),
        "architecture": args.architecture,
        "packages": packages,
        "runtime_package_metadata": metadata,
        "installed_package_test": "passed",
        "full_openssl_provider_suite": "pending separate source-built SymCrypt integration",
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
