"""Release state transitions against disposable Git repositories, never GitHub."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts import release


class VersionTests(unittest.TestCase):
    def test_stable_and_candidate_targets_share_the_development_base(self):
        for source, target in (("3.0.0-snapshot", "3.0.0"), ("3.0.0-snapshot", "3.0.0-rc.1"),
                               ("3.0.0-rc.1", "3.0.0-rc.2"), ("3.0.0-rc.2", "3.0.0")):
            release.validate_version(source, target)
        for target in ("3.0.1", "v3.0.0", "3.0.0-snapshot", "03.0.0", "3.0.0-rc.0"):
            with self.assertRaises(ValueError):
                release.validate_version("3.0.0-snapshot", target)
        with self.assertRaises(ValueError):
            release.validate_version("3.0.0-rc.2", "3.0.0-rc.1")

    def test_only_stable_releases_advance_the_patch(self):
        self.assertEqual(release.next_snapshot("3.0.0"), "3.0.1-snapshot")
        self.assertEqual(release.next_snapshot("3.0.9"), "3.0.10-snapshot")
        self.assertIsNone(release.next_snapshot("3.0.0-rc.1"))


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="qserial-release-test-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.root = self.directory / "checkout"
        self.root.mkdir()
        self.remote = self.directory / "remote.git"
        self.output = self.directory / "candidate"
        self.command("init", "--bare", str(self.remote))
        self.command("init", "-b", "main")
        self.command("config", "user.name", "Release Test")
        self.command("config", "user.email", "release-test@example.invalid")
        self.command("config", "core.autocrlf", "false")
        (self.root / "VERSION").write_text("3.0.0-snapshot\n", encoding="utf-8")
        (self.root / ".gitignore").write_text("dist/\n", encoding="utf-8")
        self.command("add", "VERSION", ".gitignore")
        self.command("commit", "-m", "Initial test")
        self.command("remote", "add", "origin", str(self.remote))
        self.command("push", "origin", "main")
        self.command("switch", "-c", "develop")
        self.command("push", "-u", "origin", "develop")
        self.initial = self.command("rev-parse", "HEAD")
        self.addCleanup(patch.stopall)
        patch.object(release, "ROOT_DIR", self.root).start()
        patch.object(release, "github_release", side_effect=lambda _: self.published).start()
        self.cli = patch.object(release, "gh", side_effect=self.github_cli).start()
        self.published = None

    def command(self, *arguments):
        return subprocess.run(["git", *arguments], cwd=self.root, check=True,
                              capture_output=True, text=True, encoding="utf-8").stdout.strip()

    def github_cli(self, *arguments):
        if arguments[1] == "create":
            self.published = {
                "draft": True, "prerelease": "--prerelease" in arguments, "assets": [],
                "name": arguments[arguments.index("--title") + 1],
                "body": Path(arguments[arguments.index("--notes-file") + 1]).read_text(encoding="utf-8"),
            }
        elif arguments[1] == "upload":
            archive = Path(arguments[3])
            self.published["assets"] = [{"name": archive.name, "size": archive.stat().st_size}]
        elif arguments[1] == "edit":
            self.published.update(
                draft=False, prerelease="--prerelease=true" in arguments,
                name=arguments[arguments.index("--title") + 1],
                body=Path(arguments[arguments.index("--notes-file") + 1]).read_text(encoding="utf-8"),
            )
        else:
            raise AssertionError(arguments)
        return ""

    def prepare(self, version="3.0.0"):
        release.prepare_release(version, "1. Improved serial sessions.", self.output,
                                confirmed_source=self.initial)
        self.candidate = release.load_candidate(self.output)
        (self.root / "dist").mkdir()
        (self.root / "dist" / f"QSerial_v{version}.zip").write_bytes(b"verified test ZIP")
        release.export_release(self.output)
        self.command("switch", "main")

    def test_stable_publish_and_bump_reuse_the_tested_commit(self):
        self.prepare()
        self.assertEqual(self.command("rev-parse", "origin/main"), self.initial)
        release.publish_release(self.output)
        self.assertFalse(self.published["draft"])
        self.assertEqual(self.command("rev-parse", "origin/main"), self.candidate["commit"])
        self.assertEqual(self.command("cat-file", "-t", "refs/tags/v3.0.0"), "tag")
        self.assertEqual(self.command("show", "v3.0.0:VERSION"), "3.0.0")
        release.finish_release(self.output)
        self.assertEqual(self.command("show", "origin/develop:VERSION"), "3.0.1-snapshot")
        self.assertEqual(self.command("rev-parse", "origin/develop^"), self.candidate["commit"])
        self.assertEqual(self.command("show", "origin/main:VERSION"), "3.0.0")

    def test_candidate_publication_does_not_increment_patch(self):
        self.prepare("3.0.0-rc.1")
        release.publish_release(self.output)
        release.finish_release(self.output)
        self.assertTrue(self.published["prerelease"])
        self.assertEqual(self.command("rev-parse", "origin/develop"), self.candidate["commit"])
        self.assertEqual(self.command("show", "origin/develop:VERSION"), "3.0.0-rc.1")

    def test_develop_advance_blocks_main_and_tag_publication(self):
        self.prepare()
        self.command("switch", "develop")
        (self.root / "feature.py").write_text("changed = True\n", encoding="utf-8")
        self.command("add", "feature.py")
        self.command("commit", "-m", "New development")
        self.command("push", "origin", "develop")
        self.command("switch", "main")
        with self.assertRaisesRegex(RuntimeError, "develop advanced"):
            release.publish_release(self.output)
        self.assertEqual(self.command("rev-parse", "origin/main"), self.initial)
        self.assertEqual(self.command("ls-remote", "--tags", "origin"), "")

    def test_existing_wrong_tag_is_not_moved(self):
        self.prepare()
        self.command("tag", "v3.0.0", self.initial)
        self.command("push", "origin", "v3.0.0")
        with self.assertRaisesRegex(RuntimeError, "different commit"):
            release.publish_release(self.output)
        self.assertEqual(self.command("rev-parse", "v3.0.0"), self.initial)

    def test_failed_upload_resumes_its_draft_without_changing_the_tag(self):
        self.prepare()
        def fail_upload(*arguments):
            if arguments[1] == "upload":
                raise RuntimeError("upload failed")
            return self.github_cli(*arguments)
        self.cli.side_effect = fail_upload
        with self.assertRaisesRegex(RuntimeError, "upload failed"):
            release.publish_release(self.output)
        self.assertTrue(self.published["draft"])
        self.assertEqual(self.command("rev-parse", "origin/develop"), self.initial)
        tag = self.command("rev-parse", "refs/tags/v3.0.0")
        self.cli.side_effect = self.github_cli
        release.publish_release(self.output)
        release.finish_release(self.output)
        self.assertFalse(self.published["draft"])
        self.assertEqual(self.command("rev-parse", "refs/tags/v3.0.0"), tag)

    def test_retries_do_not_modify_a_public_release_or_bump_twice(self):
        self.prepare()
        release.publish_release(self.output)
        release.finish_release(self.output)
        development = self.command("rev-parse", "origin/develop")
        self.cli.reset_mock()
        release.publish_release(self.output)
        release.finish_release(self.output)
        self.cli.assert_not_called()
        self.assertEqual(self.command("rev-parse", "origin/develop"), development)

    def test_resumed_draft_uses_the_confirmed_title_notes_and_release_type(self):
        self.prepare()
        self.published = {"draft": True, "prerelease": True, "assets": [],
                          "name": "Outdated title", "body": "Unconfirmed notes"}
        release.publish_release(self.output)
        self.assertEqual(self.published["name"], "QSerial v3.0.0")
        self.assertEqual(self.published["body"].strip(), "1. Improved serial sessions.")
        self.assertFalse(self.published["prerelease"])

    def test_changed_public_notes_block_recovery_without_overwriting_the_release(self):
        self.prepare()
        release.publish_release(self.output)
        self.published["body"] = "Different public notes"
        self.cli.reset_mock()
        for operation in (release.publish_release, release.finish_release):
            with self.subTest(operation=operation.__name__), self.assertRaisesRegex(RuntimeError, "confirmed"):
                operation(self.output)
        self.cli.assert_not_called()
        self.assertEqual(self.command("rev-parse", "origin/develop"), self.initial)

    def test_concurrent_development_after_publication_is_not_discarded(self):
        self.prepare()
        release.publish_release(self.output)
        self.command("switch", "develop")
        (self.root / "feature.py").write_text("changed = True\n", encoding="utf-8")
        self.command("add", "feature.py")
        self.command("commit", "-m", "Concurrent development")
        self.command("push", "origin", "develop")
        development = self.command("rev-parse", "HEAD")
        with self.assertRaisesRegex(RuntimeError, "develop advanced"):
            release.finish_release(self.output)
        self.assertEqual(self.command("rev-parse", "origin/develop"), development)
        self.assertFalse(self.published["draft"])

    def test_publication_is_required_before_development_advances(self):
        self.prepare()
        with self.assertRaisesRegex(RuntimeError, "not published"):
            release.finish_release(self.output)
        self.assertEqual(self.command("rev-parse", "origin/develop"), self.initial)

    def test_prepare_rejects_dirty_tree_and_empty_notes(self):
        with self.assertRaises(ValueError):
            release.prepare_release("3.0.0", " ", self.output, confirmed_source=self.initial)
        (self.root / "VERSION").write_text("3.0.1-snapshot\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "clean checkout"):
            release.prepare_release("3.0.1", "notes", self.output, confirmed_source=self.initial)

    def test_request_records_confirmable_inputs_without_committing_or_publishing(self):
        release.request_release("3.0.0", "1. Reviewed changes.", self.output)
        request = json.loads((self.output / "release_request.json").read_text(encoding="utf-8"))
        self.assertEqual(request, {"version": "3.0.0", "source": self.initial,
                                   "notes": "1. Reviewed changes."})
        self.assertEqual(self.command("branch", "--show-current"), "develop")
        self.assertEqual(self.command("rev-parse", "HEAD"), self.initial)
        self.assertEqual(self.command("show", "HEAD:VERSION"), "3.0.0-snapshot")
        self.cli.assert_not_called()

    def test_prepare_rejects_a_different_confirmation_sha(self):
        with self.assertRaisesRegex(RuntimeError, "confirmed source"):
            release.prepare_release("3.0.0", "notes", self.output, confirmed_source="0" * 40)
        self.assertEqual(self.command("rev-parse", "HEAD"), self.initial)

    def test_request_rejects_uncommitted_new_source(self):
        (self.root / "feature.py").write_text("changed = True\n", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "clean checkout"):
            release.request_release("3.0.0", "notes", self.output)
        self.assertFalse((self.output / "release_request.json").exists())

    def test_workflow_changes_require_orchestration_sync_before_preparation(self):
        workflows = self.root / ".github" / "workflows"
        workflows.mkdir(parents=True)
        (workflows / "ci.yml").write_text("name: Changed workflow\n", encoding="utf-8")
        self.command("add", ".github")
        self.command("commit", "-m", "Update workflow")
        self.command("push", "origin", "develop")
        with self.assertRaisesRegex(RuntimeError, "Synchronize release orchestration"):
            release.request_release("3.0.0", "notes", self.output)
        self.cli.assert_not_called()

    def test_release_helper_changes_require_orchestration_sync_before_preparation(self):
        scripts = self.root / "scripts"
        scripts.mkdir()
        (scripts / "release.py").write_text("# Updated publisher contract\n", encoding="utf-8")
        self.command("add", "scripts/release.py")
        self.command("commit", "-m", "Update publisher")
        self.command("push", "origin", "develop")
        with self.assertRaisesRegex(RuntimeError, "Synchronize release orchestration"):
            release.request_release("3.0.0", "notes", self.output)
        self.cli.assert_not_called()


class ReleaseVerificationTests(unittest.TestCase):
    def test_notes_normalize_line_endings_without_accepting_missing_content(self):
        with tempfile.TemporaryDirectory(prefix="qserial-release-info-") as directory:
            archive = Path(directory) / "QSerial_v3.0.0.zip"
            archive.write_bytes(b"tested ZIP")
            published = {
                "draft": False, "prerelease": False, "name": "QSerial v3.0.0",
                "body": "1. Improved serial sessions.\r\n",
                "assets": [{"name": archive.name, "size": archive.stat().st_size}],
            }
            release.verify_release(published, "3.0.0", archive, "1. Improved serial sessions.\n")
            published["body"] = None
            with self.assertRaisesRegex(RuntimeError, "confirmed"):
                release.verify_release(published, "3.0.0", archive, "1. Improved serial sessions.\n")


class GitHubApiTests(unittest.TestCase):
    def test_null_graphql_release_is_absent_without_a_rest_lookup(self):
        with patch.dict("os.environ", {"GITHUB_REPOSITORY": "test/repository"}):
            result = subprocess.CompletedProcess(
                ["gh", "api"], 0, json.dumps({"data": {"repository": {"release": None}}}), "",
            )
            with patch.object(release.subprocess, "run", return_value=result) as api:
                self.assertIsNone(release.github_release("3.0.0"))
            self.assertEqual(api.call_count, 1)
            self.assertEqual(api.call_args.args[0][:3], ["gh", "api", "graphql"])

    def test_draft_and_public_releases_are_read_by_resolved_id(self):
        with patch.dict("os.environ", {"GITHUB_REPOSITORY": "test/repository"}):
            for draft in (True, False):
                with self.subTest(draft=draft):
                    payloads = ({"data": {"repository": {"release": {"databaseId": 42}}}},
                                {"id": 42, "draft": draft, "assets": []})
                    responses = [subprocess.CompletedProcess(["gh", "api"], 0, json.dumps(body), "")
                                 for body in payloads]
                    with patch.object(release.subprocess, "run", side_effect=responses) as api:
                        self.assertEqual(release.github_release("3.0.0")["draft"], draft)
                    self.assertEqual(api.call_args.args[0], ["gh", "api", "repos/test/repository/releases/42"])

    def test_api_errors_are_not_reported_as_absent_releases(self):
        with patch.dict("os.environ", {"GITHUB_REPOSITORY": "test/repository"}):
            error = subprocess.CalledProcessError(1, ["gh", "api"], stderr="HTTP 403")
            with patch.object(release.subprocess, "run", side_effect=error):
                with self.assertRaises(subprocess.CalledProcessError):
                    release.github_release("3.0.0")
