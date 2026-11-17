import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "check_privacy", Path(__file__).resolve().parents[1] / "scripts/check_privacy.py"
)
assert SPEC is not None and SPEC.loader is not None
privacy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(privacy)
SCANNER = Path(privacy.__file__).resolve()


class PrivacyTests(unittest.TestCase):
    def test_personal_paths_across_platforms_and_escaped_notebooks(self):
        for value in (
            b"/" + b"Users/person/project",
            b"/" + b"home/person/project",
            b"C:" + b"\\Users\\person\\project",
            b"C:" + b"\\\\Users\\\\person\\\\project",
        ):
            with self.subTest(value=value):
                self.assertIn("personal directory", privacy.findings(value, []))

    def test_real_email_and_known_name_are_blocked(self):
        self.assertIn("email", privacy.findings(b"person" + b"@mail.test", []))
        self.assertIn(
            "local identity",
            privacy.findings(b"A Sample Person wrote this", ["sample person"]),
        )
        self.assertFalse(privacy.findings(b"person" + b"@example.test", []))

    def test_private_files_are_blocked_even_when_force_added(self):
        for path in (
            "datasets/news/train.json",
            "envs/local.env",
            ".env",
            ".audit/evidence.md",
            "private.key",
            ".privacy-identifiers.json",
        ):
            self.assertTrue(privacy.private_path(path), path)

    def test_staged_blob_and_history_cannot_be_hidden_by_clean_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def git(*args):
                return subprocess.run(
                    ["git", *args], cwd=root, capture_output=True, check=True
                )

            git("init", "-q")
            git("config", "user.name", "Contributor")
            git("config", "user.email", "contributor@users.noreply.github.com")
            file = root / "note.txt"
            file.write_text("/" + "Users/private-person/project")
            git("add", "note.txt")
            file.write_text("clean worktree")
            result = subprocess.run(
                ["python3", str(SCANNER), "staged"],
                cwd=root,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertNotIn("private-person", result.stdout + result.stderr)
            git("-c", "core.hooksPath=/dev/null", "commit", "-qm", "fixture")
            git("add", "note.txt")
            git("-c", "core.hooksPath=/dev/null", "commit", "-qm", "clean")
            result = subprocess.run(
                ["python3", str(SCANNER), "history"], cwd=root, capture_output=True
            )
            self.assertEqual(result.returncode, 1)

    def test_identity_guard_rejects_environment_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for args in (
                ("init", "-q"),
                ("config", "user.name", "Contributor"),
                ("config", "user.email", "contributor@users.noreply.github.com"),
            ):
                subprocess.run(["git", *args], cwd=root, check=True)
            command = ["python3", str(SCANNER), "identity"]
            self.assertEqual(
                subprocess.run(command, cwd=root, capture_output=True).returncode, 0
            )
            result = subprocess.run(
                command,
                cwd=root,
                capture_output=True,
                env={**os.environ, "GIT_AUTHOR_NAME": "Sample Person"},
            )
            self.assertEqual(result.returncode, 1)
            self.assertNotIn(b"Sample Person", result.stdout + result.stderr)
