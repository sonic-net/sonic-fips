#!/usr/bin/env python3
"""Compare actual provider/engine builds in two different execution roots."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from ci import audit


OUTPUTS = ("symcryptengine.so", "symcryptprovider.so")


def compare_build_roots(output, flags, prefix="//symcrypt:"):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    receipt = {"status": "running", "builds": []}
    try:
        for variant in ("short", "a_deliberately_longer_execution_root"):
            directory = output / variant
            directory.mkdir(exist_ok=True)
            parent = os.environ.get("BAZEL_REPRO_OUTPUT_ROOT", os.environ.get("RUNNER_TEMP"))
            base = Path(tempfile.mkdtemp(prefix="symcrypt-" + variant + "-", dir=parent))
            # Batch clients exit after each command. A detached Bazel server can
            # remain a zombie under the CI container's PID 1 and make shutdown
            # fail even after a successful build. Retain the fresh base and
            # its action cache without creating that server lifecycle.
            bazel = ["bazel", "--batch", "--output_base=" + str(base)]
            target = prefix + "provider_reproducibility_build"
            record = {"variant": variant, "output_base": str(base), "files": {}}
            receipt["builds"].append(record)
            with (directory / "commands.log").open("w") as log:
                if variant == "short":
                    graph_path = directory / "actions.json"
                    with graph_path.open("w") as stream:
                        subprocess.run(bazel + ["aquery", "deps(" + target + ")", *flags,
                                       "--include_file_write_contents", "--output=jsonproto"],
                                       stdout=stream, stderr=log, check=True)
                    graph = json.loads(graph_path.read_text())
                    record["audit"] = audit(graph)
                    owners = {item["id"]: item["label"] for item in graph["targets"]}
                    actions = [action for action in graph["actions"]
                               if owners[action["targetId"]].endswith(":provider_reproducibility_build")
                               and action["mnemonic"].startswith("CcCmake")]
                    assert len(actions) == 1, "expected one genuine provider CMake action"
                    assert any(item["key"] == "no-cache" for item in actions[0].get("executionInfo", [])), actions
                subprocess.run(bazel + ["build", target, *flags,
                               "--build_event_json_file=" + str(directory / "events.jsonl")],
                               stdout=log, stderr=subprocess.STDOUT, check=True)
                for name in OUTPUTS:
                    files = subprocess.check_output(bazel + ["cquery", "config(" + prefix + "repro_" + name + ", target)",
                                                    *flags, "--output=files"], text=True, stderr=log).splitlines()
                    assert len(files) == 1, files
                    # cquery paths belong to this isolated output base, not
                    # whichever invocation last changed the bazel-bin link.
                    source = base / "execroot" / "_main" / files[0]
                    destination = directory / name
                    shutil.copyfile(source, destination)
                    sections = subprocess.check_output(["readelf", "-SW", str(destination)], text=True)
                    dynamic = subprocess.check_output(["readelf", "-d", str(destination)], text=True)
                    assert ".debug_info" in sections, name
                    assert "(RPATH)" not in dynamic and "(RUNPATH)" not in dynamic, name
                    record["files"][name] = hashlib.sha256(destination.read_bytes()).hexdigest()
        left, right = receipt["builds"]
        assert left["files"] == right["files"], (left["files"], right["files"])
        receipt.update(status="passed", scope="Complete unstripped provider/engine ELF bytes including DWARF; two fresh output bases and uncached upstream CMake actions. Core integrity-key generation is unchanged, and whole runtime/debug TAR equality is not claimed.")
        return receipt
    except Exception as error:
        receipt.update(status="failed", error=str(error))
        raise
    finally:
        (output / "result.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--prefix", default="//symcrypt:")
    parser.add_argument("--bazel-arg", action="append", default=[])
    args = parser.parse_args()
    compare_build_roots(args.artifacts, args.bazel_arg, args.prefix)
