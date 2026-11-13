#!/usr/bin/env python3
"""Publish verified Debian build artifacts as immutable GitHub release assets."""

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile

REPO = "sonic-net/sonic-fips"
ARCHES = ("amd64", "arm64", "armhf")
CONTROL = Path(__file__).resolve().parents[1] / "src/SymCrypt-OpenSSL-Debian/debian/control"
# Git ref names cannot contain '~'; fail closed for versions needing tag encoding.
SAFE_VERSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+-]*\Z")
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9.+~-]*_[A-Za-z0-9][A-Za-z0-9.+:~-]*_(?:amd64|arm64|armhf|all)\.deb\Z")
SHA = re.compile(r"[0-9a-fA-F]{40}\Z")
MAX_DEB = 2 * 1024**3


class ReleaseError(Exception):
    pass


def run(args, *, missing=False):
    proc = subprocess.run(args, capture_output=True, text=True, check=False)
    if proc.returncode:
        if missing and re.search(r"\bHTTP 404\b", proc.stderr):
            return None
        # Do not echo gh output: it may contain private API data or credentials.
        raise ReleaseError(f"command failed (exit {proc.returncode}): {args[0]} {args[1]}")
    return proc.stdout


def api(path, *, missing=False, method=None, fields=()):
    cmd = ["gh", "api", f"repos/{REPO}/{path}"]
    if method:
        cmd += ["-X", method]
    for key, value in fields:
        cmd += ["-F" if key == "draft" else "-f", f"{key}={value}"]
    output = run(cmd, missing=missing)
    if output is None:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError as exc:
        raise ReleaseError("invalid GitHub API response") from exc


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def metadata(path):
    result = run(["dpkg-deb", "-f", str(path), "Package", "Version", "Architecture"])
    fields = result.splitlines()
    names = ("Package", "Version", "Architecture")
    if len(fields) != 3 or any(not line.startswith(f"{key}: ") for line, key in zip(fields, names)):
        raise ReleaseError(f"bad Debian metadata: {path.name}")
    return [line.split(": ", 1)[1] for line in fields]


def collect(root):
    packages = {}
    per_arch = {}
    versions = set()
    for arch in ARCHES:
        directory = root / f"fips-symcrypt-{arch}"
        if not directory.is_dir() or directory.is_symlink():
            raise ReleaseError(f"missing or unsafe artifact directory: {directory.name}")
        files = sorted(directory.glob("*.deb"))
        if not files:
            raise ReleaseError(f"no Debian packages in {directory.name}")
        # Reject nested .deb files; otherwise we might silently omit packages.
        if any(p.is_symlink() or not p.is_file() for p in files) or any(
            p.is_symlink() or p.is_file() for p in directory.rglob("*.deb") if p.parent != directory
        ):
            raise ReleaseError(f"nested or unsafe Debian package in {directory.name}")
        per_arch[arch] = {}
        symcrypt = 0
        for path in files:
            if not SAFE_NAME.fullmatch(path.name) or path.stat().st_size > MAX_DEB:
                raise ReleaseError(f"unsafe Debian package: {path.name}")
            name, version, package_arch = metadata(path)
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+:~-]*", version) or not re.fullmatch(r"[a-z0-9][a-z0-9+.-]*", name):
                raise ReleaseError(f"unsafe Debian metadata: {path.name}")
            if package_arch not in (arch, "all") or path.name != f"{name}_{version}_{package_arch}.deb":
                raise ReleaseError(f"Debian filename/architecture mismatch: {path.name}")
            if name == "symcrypt-openssl":
                if not SAFE_VERSION.fullmatch(version):
                    raise ReleaseError("unsafe SymCrypt version for GitHub tag")
                symcrypt += 1
                if package_arch != arch:
                    raise ReleaseError(f"symcrypt-openssl must be built for {arch}")
                versions.add(version)
            hashed = digest(path)
            if path.name in packages and packages[path.name][1] != hashed:
                raise ReleaseError(f"conflicting duplicate package: {path.name}")
            packages[path.name] = (path, hashed)
            per_arch[arch][path.name] = hashed
        if symcrypt != 1:
            raise ReleaseError(f"expected exactly one symcrypt-openssl package for {arch}")
    if len(versions) != 1:
        raise ReleaseError(f"inconsistent symcrypt-openssl Version: {sorted(versions)}")
    # All 'all' packages must occur in every artifact, with identical bytes.
    all_names = {n for n in packages if n.endswith("_all.deb")}
    for arch in ARCHES:
        if not all_names.issubset(per_arch[arch]):
            raise ReleaseError(f"inconsistent architecture-independent packages: {arch}")
    return versions.pop(), per_arch, {name: h for name, (_, h) in packages.items()}


def expected_version():
    matches = re.findall(r"^Version: (\S+)$", CONTROL.read_text(encoding="utf-8"), re.MULTILINE)
    if len(matches) != 1 or not SAFE_VERSION.fullmatch(matches[0]):
        raise ReleaseError("invalid source SymCrypt Debian version")
    return matches[0]


def create_assets(root, per_arch, dest):
    assets = {}
    for arch in ARCHES:
        name = f"fips-symcrypt-{arch}.tar.gz"
        path = dest / name
        with path.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
                with tarfile.open(fileobj=zipped, mode="w") as archive:
                    for filename in sorted(per_arch[arch]):
                        source = root / f"fips-symcrypt-{arch}" / filename
                        info = tarfile.TarInfo(filename)
                        info.size = source.stat().st_size
                        info.mode = 0o644
                        info.mtime = 0
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        with source.open("rb") as inp:
                            archive.addfile(info, inp)
        assets[name] = digest(path)
    sums = dest / "SHA256SUMS"
    sums.write_text("".join(f"{h}  {name}\n" for name, h in sorted(assets.items())), encoding="ascii")
    return assets


def validate_assets(directory, expected_per_arch=None):
    expected_names = {f"fips-symcrypt-{a}.tar.gz" for a in ARCHES}
    actual = {p.name for p in directory.iterdir()}
    if actual != expected_names | {"SHA256SUMS"}:
        raise ReleaseError("release assets missing or unexpected")
    sums = directory / "SHA256SUMS"
    if not sums.is_file() or sums.is_symlink():
        raise ReleaseError("unsafe SHA256SUMS")
    lines = sums.read_text(encoding="ascii").splitlines()
    if any((directory / name).is_symlink() or not (directory / name).is_file() for name in expected_names):
        raise ReleaseError("unsafe release archive")
    expected_lines = [f"{digest(directory / name)}  {name}" for name in sorted(expected_names)]
    if lines != expected_lines:
        raise ReleaseError("release SHA256SUMS mismatch")
    packages = {}
    archive_packages = {}
    for arch in ARCHES:
        archive = directory / f"fips-symcrypt-{arch}.tar.gz"
        if archive.is_symlink() or not archive.is_file():
            raise ReleaseError("unsafe release archive")
        with tarfile.open(archive, "r:gz") as tar:
            members = tar.getmembers()
            if not members or len(members) > 10000:
                raise ReleaseError("empty or excessive release archive")
            seen = set()
            archive_packages[arch] = {}
            for member in members:
                name = member.name
                if (not member.isfile() or not SAFE_NAME.fullmatch(name) or name in seen
                        or member.size > MAX_DEB or not name.endswith((f"_{arch}.deb", "_all.deb"))):
                    raise ReleaseError("unsafe release archive entry")
                seen.add(name)
                stream = tar.extractfile(member)
                if stream is None:
                    raise ReleaseError("missing release archive entry")
                h = hashlib.sha256()
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    h.update(block)
                if name in packages and packages[name] != h.hexdigest():
                    raise ReleaseError(f"conflicting release package: {name}")
                packages[name] = h.hexdigest()
                archive_packages[arch][name] = h.hexdigest()
    all_names = {n for n in packages if n.endswith("_all.deb")}
    if any(not all_names.issubset(archive_packages[arch]) for arch in ARCHES):
        raise ReleaseError("inconsistent release architecture-independent packages")
    if expected_per_arch is not None and archive_packages != expected_per_arch:
        raise ReleaseError("redownloaded package content/architecture mismatch")
    return packages


def release(tag):
    return api(f"releases/tags/{tag}", missing=True)


def compare(tag, wanted):
    found = release(tag)
    if found is None:
        return None
    if found.get("draft") or found.get("prerelease"):
        raise ReleaseError(f"existing draft/prerelease {tag}: manual inspection required")
    with tempfile.TemporaryDirectory() as temp:
        run(["gh", "release", "download", tag, "--repo", REPO, "--dir", temp])
        actual = validate_assets(Path(temp))
    if {a.get("name") for a in found.get("assets", [])} != {
        "SHA256SUMS", *(f"fips-symcrypt-{a}.tar.gz" for a in ARCHES)
    }:
        raise ReleaseError(f"unexpected asset list on release {tag}")
    return actual == wanted


def require_ci():
    environment = os.environ
    if not (environment.get("BUILD_SOURCEBRANCH") == "refs/heads/main"
            and environment.get("BUILD_REASON") != "PullRequest"
            and environment.get("BUILD_REPOSITORY_NAME") == REPO
            and environment.get("BUILD_REPOSITORY_URI", "").rstrip("/").removesuffix(".git") == f"https://github.com/{REPO}"
            and environment.get("SYSTEM_PULLREQUEST_ISFORK", "").lower() != "true"):
        raise ReleaseError("not a canonical main-branch non-PR build")


def publish(args):
    if args.require_ci:
        require_ci()
    if not re.fullmatch(r"[0-9]+", args.build_id):
        raise ReleaseError("Azure build ID must be numeric")
    if not SHA.fullmatch(args.commit):
        raise ReleaseError("source commit must be a full Git SHA")
    if not os.environ.get("GH_TOKEN"):
        raise ReleaseError("GH_TOKEN is required (never put credentials in arguments)")
    root = args.artifacts.resolve(strict=True)
    version, per_arch, wanted = collect(root)
    if version != expected_version():
        raise ReleaseError(f"SymCrypt artifact version {version} differs from source control")
    default_tag = version
    fallback_tag = f"{version}-build-{args.build_id}"
    # Check before any mutation, including a possible tag without an associated release.
    match = compare(default_tag, wanted)
    if match is True:
        print(f"Skipped: identical packages already released at {default_tag}")
        return
    tag = fallback_tag if match is False else default_tag
    if match is False:
        fallback_match = compare(tag, wanted)
        if fallback_match is True:
            print(f"Skipped: identical packages already released at {tag}")
            return
        if fallback_match is False:
            raise ReleaseError(f"fallback release {tag} differs: refusing overwrite")
    if api(f"git/ref/tags/{tag}", missing=True) is not None:
        raise ReleaseError(f"tag {tag} exists without a usable release: refusing overwrite")
    with tempfile.TemporaryDirectory() as temp:
        staging = Path(temp) / "staging"
        staging.mkdir()
        create_assets(root, per_arch, staging)
        if any((staging / f"fips-symcrypt-{arch}.tar.gz").stat().st_size >= MAX_DEB for arch in ARCHES):
            raise ReleaseError("release archive exceeds GitHub's 2 GiB asset limit")
        if validate_assets(staging, per_arch) != wanted:
            raise ReleaseError("local archive verification failed")
        # Explicit ref creation fails atomically on an existing tag. Never update a ref.
        api("git/refs", method="POST", fields=(("ref", f"refs/tags/{tag}"), ("sha", args.commit)))
        created = api("releases", method="POST", fields=(
            ("tag_name", tag), ("name", tag), ("draft", "true"),
            ("body", f"Packages from Azure build {args.build_id}, source {args.commit}."),
        ))
        if created.get("tag_name") != tag or not created.get("draft") or not isinstance(created.get("id"), int):
            raise ReleaseError("unexpected draft creation response; do not publish")
        run(["gh", "release", "upload", tag, *(str(staging / n) for n in sorted(p.name for p in staging.iterdir())), "--repo", REPO])
        downloaded = Path(temp) / "downloaded"
        downloaded.mkdir()
        run(["gh", "release", "download", tag, "--repo", REPO, "--dir", str(downloaded)])
        if validate_assets(downloaded, per_arch) != wanted:
            raise ReleaseError("redownloaded package content mismatch; draft left unpublished")
        current = release(tag)
        if (not current or current.get("id") != created["id"] or not current.get("draft")
                or {a.get("name") for a in current.get("assets", [])} != {p.name for p in staging.iterdir()}):
            raise ReleaseError("draft changed during verification; refusing to publish")
        ref = api(f"git/ref/tags/{tag}")
        if ref.get("object", {}).get("sha", "").lower() != args.commit.lower():
            raise ReleaseError("tag target changed; refusing to publish")
        updated = api(f"releases/{created['id']}", method="PATCH", fields=(("draft", "false"),))
        if updated.get("draft") is not False or updated.get("tag_name") != tag:
            raise ReleaseError("publish response unexpected; inspect release manually")
        print(f"Published https://github.com/{REPO}/releases/tag/{tag}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True, help="directory containing three current-build artifact directories")
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--commit", required=True, help="40-digit source commit SHA")
    parser.add_argument("--require-ci", action="store_true", help="enforce canonical Azure main-build identity")
    args = parser.parse_args()
    try:
        publish(args)
    except (ReleaseError, OSError, ValueError, tarfile.TarError) as exc:
        print(f"release failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
