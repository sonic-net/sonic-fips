#!/usr/bin/env python3
"""Record the maintained SONiC registry inputs used by local builds and CI."""

import argparse
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[2]
MAIN = "https://raw.githubusercontent.com/securely1g/sonic-bazel-registry/main"


def record(artifacts, snapshot=None):
    registry = MAIN
    configuration = (ROOT / ".bazelrc").read_text()
    endpoints = [line for line in configuration.splitlines()
                 if "--registry=" in line and "securely1g/sonic-bazel-registry/" in line]
    if endpoints != ["common --registry=" + MAIN]:
        raise ValueError("Expected exactly the canonical SONiC main registry endpoint")
    if snapshot:
        if not re.fullmatch(r"[0-9a-f]{40}", snapshot):
            raise ValueError("Draft registry validation requires a full commit SHA")
        registry = MAIN.removesuffix("main") + snapshot
        revision = snapshot
    else:
        ref = "refs/heads/main"
        advertised = subprocess.check_output(
            ["git", "ls-remote", "https://github.com/securely1g/sonic-bazel-registry.git", ref],
            text=True).split()
        if len(advertised) != 2 or advertised[1] != ref or not re.fullmatch(r"[0-9a-f]{40}", advertised[0]):
            raise ValueError("Could not determine the selected registry branch revision")
        revision = advertised[0]
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "declared.bazelrc").write_text(configuration)
    effective = artifacts.resolve() / "effective.bazelrc"
    selected = configuration.replace(MAIN, registry)
    effective.write_text(selected)
    if snapshot:
        # CI restores this temporary selection before checking its source tree.
        # The committed local-build default remains the maintained main branch.
        (ROOT / ".bazelrc").write_text(selected)
    (artifacts / "registry-inputs.json").write_text(json.dumps({
        "declared_registry": MAIN, "registry": registry,
        "observed_revision": revision, "draft_validation": registry != MAIN,
    }, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifacts", type=Path)
    parser.add_argument("--snapshot", help="temporary immutable registry commit for draft CI")
    args = parser.parse_args()
    record(args.artifacts, args.snapshot)
