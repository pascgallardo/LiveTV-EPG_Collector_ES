"""Tests for the EPG workflow in TV-Spain-EPG.yml.

The schedule is the part worth pinning: GitHub cron cannot express "every 48
hours", so `0 8 */2 * *` is the closest it gets and the drift it introduces at a
month boundary is a deliberate, documented trade-off rather than an accident.

Parsing is textual on purpose, for the same reason as in
`test_workflow_schedule.py`: PyYAML is not a dependency of this project.
"""
import pathlib
import re
import unittest
from pathlib import Path

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "TV-Spain-EPG.yml"
MERGER = REPO_ROOT / "BugsfreeMain" / "TV-Spain-EPG.py"


def workflow_text():
    return WORKFLOW.read_text(encoding="utf-8")


def cron_entries():
    """Return every `- cron: '<expr>'` entry of the schedule block."""
    lines = workflow_text().splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == "schedule:")
    except StopIteration:
        raise AssertionError("TV-Spain-EPG.yml has no schedule block")
    entries = []
    for line in lines[start + 1:]:
        stripped = line.strip()
        if stripped.startswith("#"):
            continue  # the block documents the choice before the cron entries
        if not stripped.startswith("- cron:"):
            break
        entries.append(stripped.split(":", 1)[1].strip().strip("'\""))
    return entries


class TestEpgSchedule(unittest.TestCase):
    def test_workflow_exists(self):
        self.assertTrue(WORKFLOW.is_file(), "TV-Spain-EPG.yml is missing")

    def test_single_cron_every_two_days_at_eight_utc(self):
        # Cron has no 48-hour step, so the even days of the month is the standard
        # way to ask for it.
        self.assertEqual(cron_entries(), ["0 8 */2 * *"])

    def test_the_day_step_is_the_one_that_makes_it_every_other_day(self):
        self.assertEqual(cron_entries()[0].split()[2], "*/2")

    def test_the_drift_at_a_month_boundary_is_documented(self):
        # 0 8 */2 * * restarts on the 1st, so the gap from the 30th to the 1st is
        # 24 h rather than 48 h. Anyone reading the file must be able to see that
        # it is known rather than assumed.
        text = workflow_text()
        self.assertIn("drift", text.lower())
        self.assertRegex(text, r"30th|boundary")

    def test_manual_trigger_is_kept(self):
        self.assertIn("workflow_dispatch", workflow_text())

    def test_real_publish_time_is_logged(self):
        text = workflow_text()
        self.assertIn("Europe/Madrid", text)
        self.assertIn("date -u", text)

    def test_the_banner_advertises_the_even_day_slot(self):
        self.assertIn("08:00 UTC", workflow_text())


class TestEpgWorkflowSteps(unittest.TestCase):
    def setUp(self):
        self.text = workflow_text()

    def test_it_runs_the_merger_script(self):
        self.assertIn("BugsfreeMain/TV-Spain-EPG.py", self.text)

    def test_it_runs_the_test_suite_first(self):
        self.assertIn("python -m unittest discover -s tests -t .", self.text)

    def test_it_installs_the_requirements(self):
        self.assertIn("pip install -r requirements.txt", self.text)

    def test_it_commits_both_published_files(self):
        self.assertIn("git add LiveTV/Spain/LiveTV.xml LiveTV/Spain/LiveTV.xml.gz",
                      self.text)

    def test_it_does_not_commit_the_playlist(self):
        # The playlist belongs to the M3U collector's daily run. Committing it
        # here would make two workflows race for the same files.
        add_line = next(line for line in self.text.splitlines()
                        if line.strip().startswith("git add"))
        self.assertNotIn("LiveTV.m3u", add_line)
        self.assertNotIn("LiveTV.json", add_line)
        self.assertNotIn("epg-sources.json", add_line)

    def test_an_empty_result_does_not_become_a_commit(self):
        self.assertIn("git diff --cached --quiet", self.text)

    def test_it_rebases_before_pushing(self):
        # The M3U collector commits to the same branch on its own schedule.
        self.assertIn("git pull --rebase", self.text)

    def test_it_can_write_to_the_repository(self):
        self.assertIn("contents: write", self.text)

    def test_the_job_has_a_timeout(self):
        # The merge downloads tens of megabytes; a hung request must not hold a
        # runner for the default six hours.
        self.assertIn("timeout-minutes:", self.text)

    def test_it_is_independent_from_the_m3u_collector(self):
        # The playlist is an input, not something this workflow rebuilds, so it
        # must not call the M3U workflow or the index generator.
        self.assertNotIn("TV-Spain.yml", self.text)
        self.assertNotIn("update-indexes", self.text)
        self.assertNotIn("generate_indexes.py", self.text)


class TestSchedulesDoNotCollide(unittest.TestCase):
    """The two workflows must not fire at the same instant.

    The M3U collector rewrites the playlist and the manifest, and this merger
    reads both. Running them simultaneously could hand the merger a playlist
    that is only half written, so the two crons are checked to differ.
    """

    COLLECTOR = REPO_ROOT / ".github" / "workflows" / "TV-Spain.yml"

    def only_cron(self, text):
        found = re.findall(r"- cron: '([^']+)'", text)
        self.assertEqual(len(found), 1, "each workflow has exactly one cron")
        return found[0]

    def test_the_two_workflows_use_different_crons(self):
        collector = self.only_cron(self.COLLECTOR.read_text(encoding="utf-8"))
        guide = self.only_cron(workflow_text())

        self.assertNotEqual(collector, guide)

    def test_the_collector_still_runs_every_day(self):
        # The guide is refreshed twice a day at most; the playlist is what
        # decides which tvg-id exist, so it has to stay on the daily slot.
        collector = self.only_cron(self.COLLECTOR.read_text(encoding="utf-8"))
        self.assertEqual(collector.split()[2], "*")


if __name__ == "__main__":
    unittest.main()
