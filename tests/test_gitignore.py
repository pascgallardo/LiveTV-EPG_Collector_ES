"""Tests for the repository .gitignore.

The collector is imported by path, so Python writes __pycache__ directories
inside the repository on every CI run. These tests make sure those artefacts stay
ignored and, just as important, that the patterns never start hiding a file the
workflow actually needs to commit.
"""
import pathlib
import subprocess
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
GITIGNORE = REPO_ROOT / ".gitignore"


def git_ignored(*paths):
    """Return the subset of *paths* that git reports as ignored."""
    result = subprocess.run(
        ["git", "check-ignore"] + list(paths),
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    if result.returncode not in (0, 1):
        raise AssertionError(f"git check-ignore failed: {result.stderr.strip()}")
    return {line for line in result.stdout.splitlines() if line}


class TestGitignore(unittest.TestCase):
    def test_gitignore_exists(self):
        self.assertTrue(GITIGNORE.is_file(), ".gitignore is missing")

    def test_python_bytecode_caches_are_ignored(self):
        ignored = git_ignored(
            "BugsfreeMain/__pycache__",
            "tests/__pycache__",
            "BugsfreeMain/TV-Spain.cpython-312.pyc",
        )
        self.assertEqual(ignored, {
            "BugsfreeMain/__pycache__",
            "tests/__pycache__",
            "BugsfreeMain/TV-Spain.cpython-312.pyc",
        })

    def test_published_data_files_are_not_ignored(self):
        # These are the exact paths the update-files and update-indexes jobs
        # stage; ignoring any of them would make the workflow silently commit
        # nothing.
        published = [
            "LiveTV/Spain/LiveTV.m3u",
            "LiveTV/Spain/LiveTV.txt",
            "LiveTV/Spain/LiveTV.json",
            "LiveTV/Spain/LiveTV",
            "LiveTV/index.json",
        ]
        self.assertEqual(git_ignored(*published), set())

    def test_no_tracked_file_is_ignored(self):
        # A pattern that matches something already committed is a sign the
        # .gitignore is too broad; it should be fixed rather than tolerated.
        result = subprocess.run(
            ["git", "ls-files", "-i", "-c", "--exclude-standard"],
            cwd=REPO_ROOT, capture_output=True, text=True, check=True,
        )
        offenders = [line for line in result.stdout.splitlines() if line]
        self.assertEqual(offenders, [], "tracked files are matched by .gitignore")


if __name__ == "__main__":
    unittest.main()
