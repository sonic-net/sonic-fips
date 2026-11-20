"""Offline publisher tests using a stateful gh/dpkg-deb command mock."""
import importlib.util
import json
import os
import subprocess
import shutil
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/publish_github_release.py"
spec = importlib.util.spec_from_file_location("publisher", SCRIPT)
pub = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pub)
COMMIT = "a" * 40
VERSION = "1.8.0-24-gd744cf2-3"


class FakeCLI:
    def __init__(self):
        self.refs = {}
        self.releases = {}
        self.uploads = {}
        self.next_id = 1
        self.writes = []
        self.corrupt_download = False
        self.fail_upload = False

    def __call__(self, args, *, missing=False):
        if args[0] == "dpkg-deb":
            package, version, arch = Path(args[2]).name[:-4].split("_")
            return f"Package: {package}\nVersion: {version}\nArchitecture: {arch}\n"
        assert args[0] == "gh", args
        if args[1] == "release":
            action, tag = args[2:4]
            if action == "upload":
                if self.fail_upload:
                    raise pub.ReleaseError("mock upload failed")
                if tag in self.uploads:
                    raise pub.ReleaseError("asset already exists")
                self.uploads[tag] = {Path(p).name: Path(p).read_bytes() for p in args[4:args.index("--repo")]}
                self.releases[tag]["assets"] = [{"name": n} for n in self.uploads[tag]]
                self.writes.append("upload")
                return ""
            if action == "download":
                directory = Path(args[args.index("--dir") + 1])
                for name, content in self.uploads[tag].items():
                    (directory / name).write_bytes(content)
                if self.corrupt_download:
                    (directory / "fips-symcrypt-amd64.tar.gz").write_bytes(b"corrupt")
                return ""
            raise AssertionError(args)
        assert args[1] == "api", args
        path = args[2].removeprefix("repos/sonic-net/sonic-fips/")
        method = args[args.index("-X") + 1] if "-X" in args else "GET"
        fields = dict(arg.split("=", 1) for i, arg in enumerate(args) if i and args[i - 1] in ("-f", "-F"))
        if method != "GET":
            self.writes.append(f"{method} {path}")
        if path.startswith("releases/tags/"):
            tag = path[len("releases/tags/"):]
            if tag not in self.releases:
                if missing:
                    return None
                raise pub.ReleaseError("mock missing release")
            return json.dumps(self.releases[tag])
        if path.startswith("git/ref/tags/"):
            tag = path[len("git/ref/tags/"):]
            if tag not in self.refs:
                if missing:
                    return None
                raise pub.ReleaseError("mock missing ref")
            return json.dumps({"object": {"sha": self.refs[tag]}})
        if path == "git/refs" and method == "POST":
            tag = fields["ref"].removeprefix("refs/tags/")
            if tag in self.refs:
                raise pub.ReleaseError("tag already exists")
            self.refs[tag] = fields["sha"]
            return json.dumps({"ref": fields["ref"]})
        if path == "releases" and method == "POST":
            tag = fields["tag_name"]
            assert tag in self.refs and tag not in self.releases
            release = {"id": self.next_id, "tag_name": tag, "draft": True, "prerelease": False, "assets": []}
            self.next_id += 1
            self.releases[tag] = release
            return json.dumps(release)
        if path.startswith("releases/") and method == "PATCH":
            release = next(r for r in self.releases.values() if r["id"] == int(path.split("/")[1]))
            release["draft"] = False
            return json.dumps(release)
        raise AssertionError(args)


class PublisherTests(unittest.TestCase):
    def setUp(self):
        self.real_run = pub.run
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cli = FakeCLI()
        self.mock_run = patch.object(pub, "run", side_effect=self.cli)
        self.mock_run.start()
        self.addCleanup(self.mock_run.stop)
        self.token = patch.dict(os.environ, {"GH_TOKEN": "fake-token"})
        self.token.start()
        self.addCleanup(self.token.stop)
        self.args = type("Args", (), {"artifacts": self.root, "build_id": "123", "commit": COMMIT, "require_ci": False})()
        for arch in pub.ARCHES:
            directory = self.root / f"fips-symcrypt-{arch}"
            directory.mkdir()
            (directory / f"symcrypt-openssl_{VERSION}_{arch}.deb").write_bytes(arch.encode())
            (directory / "shared_1_all.deb").write_bytes(b"same")

    def publish(self):
        pub.publish(self.args)

    def test_create_and_skip_identical_default(self):
        self.publish()
        tag = VERSION
        self.assertFalse(self.cli.releases[tag]["draft"])
        self.assertEqual(self.cli.refs[tag], COMMIT)
        self.assertEqual(set(self.cli.uploads[tag]), {"SHA256SUMS", *(f"fips-symcrypt-{a}.tar.gz" for a in pub.ARCHES)})
        before = list(self.cli.writes)
        self.publish()
        self.assertEqual(before, self.cli.writes)

    def test_changed_packages_create_fallback_and_skip_retry(self):
        self.publish()
        path = self.root / "fips-symcrypt-amd64" / f"symcrypt-openssl_{VERSION}_amd64.deb"
        path.write_bytes(b"new")
        self.publish()
        self.assertIn(f"{VERSION}-build-123", self.cli.releases)
        before = list(self.cli.writes)
        self.publish()
        self.assertEqual(before, self.cli.writes)
        path.write_bytes(b"other")
        with self.assertRaisesRegex(pub.ReleaseError, "fallback release .* differs"):
            self.publish()
        self.assertEqual(before, self.cli.writes)

    def test_new_source_version_becomes_release_tag(self):
        future = "1.8.0-24-gd744cf2-4"
        control = self.root / "control"
        control.write_text(f"Package: symcrypt-openssl\nVersion: {future}\n")
        for arch in pub.ARCHES:
            directory = self.root / f"fips-symcrypt-{arch}"
            (directory / f"symcrypt-openssl_{VERSION}_{arch}.deb").rename(
                directory / f"symcrypt-openssl_{future}_{arch}.deb")
        with patch.object(pub, "CONTROL", control):
            self.publish()
        self.assertIn(future, self.cli.releases)

    def test_source_version_mismatch_fails_before_git_write(self):
        control = self.root / "control"
        control.write_text("Package: symcrypt-openssl\nVersion: 1.8.0-24-gd744cf2-4\n")
        with patch.object(pub, "CONTROL", control):
            with self.assertRaisesRegex(pub.ReleaseError, "differs from source control"):
                self.publish()
        self.assertEqual(self.cli.writes, [])

    def test_existing_orphan_tag_and_draft_fail_without_writes(self):
        self.cli.refs[VERSION] = COMMIT
        with self.assertRaisesRegex(pub.ReleaseError, "exists without"):
            self.publish()
        self.cli.refs.clear()
        self.cli.releases[VERSION] = {"id": 4, "draft": True}
        with self.assertRaisesRegex(pub.ReleaseError, "existing draft"):
            self.publish()
        self.assertEqual(self.cli.writes, [])

    def test_corrupted_redownload_leaves_draft(self):
        self.cli.corrupt_download = True
        with self.assertRaises(pub.ReleaseError):
            self.publish()
        self.assertTrue(self.cli.releases[VERSION]["draft"])
        self.assertFalse(any(x.startswith("PATCH") for x in self.cli.writes))

    def test_upload_failure_does_not_publish(self):
        self.cli.fail_upload = True
        with self.assertRaises(pub.ReleaseError):
            self.publish()
        self.assertTrue(self.cli.releases[VERSION]["draft"])

    def test_bad_version_arch_duplicate_and_missing_all(self):
        root = self.root / "fips-symcrypt-arm64"
        correct = root / f"symcrypt-openssl_{VERSION}_arm64.deb"
        correct.rename(root / "symcrypt-openssl_1.2_arm64.deb")
        with self.assertRaisesRegex(pub.ReleaseError, "inconsistent symcrypt-openssl Version"):
            self.publish()
        (root / "symcrypt-openssl_1.2_arm64.deb").rename(correct)
        (root / "wrong_1_amd64.deb").write_bytes(b"x")
        with self.assertRaisesRegex(pub.ReleaseError, "mismatch"):
            self.publish()
        (root / "wrong_1_amd64.deb").unlink()
        (root / "shared_1_all.deb").write_bytes(b"different")
        with self.assertRaisesRegex(pub.ReleaseError, "conflicting duplicate"):
            self.publish()
        (root / "shared_1_all.deb").unlink()
        with self.assertRaisesRegex(pub.ReleaseError, "inconsistent architecture-independent"):
            self.publish()
        self.assertEqual(self.cli.writes, [])

    def test_symlink_and_nested_deb_rejected(self):
        source = self.root / "fips-symcrypt-amd64" / "shared_1_all.deb"
        target = self.root / "fips-symcrypt-arm64" / "extra_1_all.deb"
        target.symlink_to(source)
        with self.assertRaisesRegex(pub.ReleaseError, "unsafe Debian"):
            self.publish()
        target.unlink()
        nested = target.parent / "nested"
        nested.mkdir()
        (nested / "extra_1_all.deb").write_bytes(b"x")
        with self.assertRaisesRegex(pub.ReleaseError, "nested"):
            self.publish()

    def test_reject_bad_id_commit_and_ci_identity(self):
        self.args.build_id = "12;echo"
        with self.assertRaisesRegex(pub.ReleaseError, "numeric"):
            self.publish()
        self.args.build_id = "123"
        self.args.commit = "bad"
        with self.assertRaisesRegex(pub.ReleaseError, "full Git SHA"):
            self.publish()
        self.args.commit = COMMIT
        self.args.require_ci = True
        with self.assertRaisesRegex(pub.ReleaseError, "canonical"):
            self.publish()
        with patch.dict(os.environ, {
            "BUILD_SOURCEBRANCH": "refs/heads/main", "BUILD_REASON": "IndividualCI",
            "BUILD_REPOSITORY_NAME": pub.REPO, "BUILD_REPOSITORY_URI": f"https://github.com/{pub.REPO}",
            "SYSTEM_PULLREQUEST_ISFORK": "True",
        }):
            with self.assertRaisesRegex(pub.ReleaseError, "canonical"):
                self.publish()
        self.assertEqual(self.cli.writes, [])

    def test_existing_corrupt_release_fails_closed(self):
        self.publish()
        original = list(self.cli.writes)
        self.cli.uploads[VERSION]["SHA256SUMS"] = b"wrong\n"
        with self.assertRaisesRegex(pub.ReleaseError, "SHA256SUMS mismatch"):
            self.publish()
        self.assertEqual(original, self.cli.writes)

    def test_tag_target_change_prevents_publish(self):
        original = self.cli.__call__

        def move_ref(args, *, missing=False):
            if args[:2] == ["gh", "release"] and args[2] == "download" and args[3] == VERSION:
                self.cli.refs[VERSION] = "b" * 40
            return original(args, missing=missing)

        with patch.object(pub, "run", side_effect=move_ref):
            with self.assertRaisesRegex(pub.ReleaseError, "tag target changed"):
                self.publish()
        self.assertTrue(self.cli.releases[VERSION]["draft"])

    @unittest.skipUnless(shutil.which("dpkg-deb"), "dpkg-deb unavailable")
    def test_real_dpkg_metadata_output(self):
        folder = self.root / "real-pkg"
        (folder / "DEBIAN").mkdir(parents=True)
        (folder / "DEBIAN" / "control").write_text(
            "Package: symcrypt-openssl\nVersion: 1.8.0-24-gd744cf2-3\n"
            "Architecture: arm64\nMaintainer: Test <test@example.invalid>\nDescription: test\n"
        )
        archive = self.root / "sample.deb"
        subprocess.run(["dpkg-deb", "--build", str(folder), str(archive)], check=True, capture_output=True)
        with patch.object(pub, "run", wraps=self.real_run):
            self.assertEqual(pub.metadata(archive), ["symcrypt-openssl", VERSION, "arm64"])

    def test_archive_deterministic(self):
        _, per_arch, _ = pub.collect(self.root)
        a, b = self.root / "a", self.root / "b"
        a.mkdir(); b.mkdir()
        self.assertEqual(pub.create_assets(self.root, per_arch, a), pub.create_assets(self.root, per_arch, b))
        self.assertEqual(pub.validate_assets(a), pub.validate_assets(b))


if __name__ == "__main__":
    unittest.main()
