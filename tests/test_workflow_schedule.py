"""Tests for the scheduling configuration in TV-Spain.yml.

GitHub's `schedule` trigger is best effort: it is honoured, the start time is not.
These tests pin down the decisions taken after measuring 978 scheduled runs
(April-September 2026, median delay 171 min at 00:00Z, 154 min at 08:00Z and
103 min at 16:00Z, and never less than 28 min):

* a single cron at 16:00 UTC, the least congested slot;
* no time gate, because a +/-30 min window could never have passed;
* no leftover reference to the removed scripts/madrid_noon_gate.py.

Parsing is textual on purpose: PyYAML is not a dependency of this project, so a
malformed workflow would not be caught by a schema check here.
"""
import pathlib
import unittest
from pathlib import Path

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "TV-Spain.yml"
REMOVED_GATE = REPO_ROOT / "scripts" / "madrid_noon_gate.py"


def workflow_text():
    return WORKFLOW.read_text(encoding="utf-8")


def cron_entries():
    """Return every `- cron: '<expr>'` entry of the schedule block."""
    lines = workflow_text().splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == "schedule:")
    except StopIteration:
        raise AssertionError("TV-Spain.yml has no schedule block")
    entries = []
    for line in lines[start + 1:]:
        stripped = line.strip()
        if stripped.startswith("#"):
            continue  # the block documents the choice before the cron entries
        if not stripped.startswith("- cron:"):
            break
        entries.append(stripped.split(":", 1)[1].strip().strip("'\""))
    return entries


class TestSchedule(unittest.TestCase):
    def test_workflow_exists(self):
        self.assertTrue(WORKFLOW.is_file(), "TV-Spain.yml is missing")

    def test_single_cron_at_sixteen_utc(self):
        self.assertEqual(cron_entries(), ["0 16 * * *"])

    def test_cron_is_expressed_in_utc(self):
        # GitHub cron has no timezone field; a non-zero hour would silently move
        # the run away from the measured least-congested slot.
        self.assertEqual(cron_entries()[0].split()[1], "16")

    def test_manual_trigger_is_kept(self):
        self.assertIn("workflow_dispatch", workflow_text())

    def test_no_time_gate_job(self):
        text = workflow_text()
        self.assertNotIn("madrid_noon_gate", text)
        self.assertNotIn("needs: gate", text)
        self.assertNotIn("needs.gate.outputs", text)

    def test_gate_script_is_gone(self):
        self.assertFalse(
            REMOVED_GATE.exists(),
            "scripts/madrid_noon_gate.py should have been removed together with the gate",
        )

    def test_gate_script_is_not_referenced_anywhere(self):
        for path in REPO_ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if path.suffix in {".m3u", ".txt", ".json"} or path.name in {"LiveTV"}:
                continue  # generated channel data
            if path.resolve() == Path(__file__).resolve():
                continue  # this file names the gate on purpose
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            self.assertNotIn("madrid_noon_gate", content, f"{path} still references the gate")

    def test_jobs_are_well_formed(self):
        text = workflow_text()
        jobs_at = text.index("\njobs:\n")
        body = text[jobs_at:]
        # `update-files` runs unconditionally; `update-indexes` still follows it.
        self.assertIn("  update-files:\n", body)
        self.assertIn("  update-indexes:\n", body)
        self.assertIn("needs: update-files", body)
        self.assertLess(body.index("update-files:"), body.index("update-indexes:"))

    def test_real_publish_time_is_logged(self):
        # The workflow records the moment it really started, in UTC and in Madrid,
        # because the cron minute is not the publication time.
        text = workflow_text()
        self.assertIn("Europe/Madrid", text)
        self.assertIn("date -u", text)


if __name__ == "__main__":
    unittest.main()
