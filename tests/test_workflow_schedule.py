"""Tests for the scheduling configuration in TV-Spain.yml.

GitHub's `schedule` trigger is best effort: it is honoured, the start time is not.
These tests pin down the decisions taken after measuring 978 scheduled runs
(April-September 2026, median delay 171 min at 00:00Z, 154 min at 08:00Z and
103 min at 16:00Z, and never less than 28 min):

* a single cron at 08:00 UTC. The slot was moved 8 h earlier than the measured
  least congested one (16:00Z) to publish the lists in the middle of the Spanish
  afternoon; the delay is a queue that has to be paid either way, so shifting the
  cron shifts the publication by the same amount;
* no time gate, because a +/-30 min window could never have passed;
* no leftover reference to the removed scripts/madrid_noon_gate.py;
* one hour everywhere, so moving the cron cannot leave the banner or the README
  advertising the previous slot.

Parsing is textual on purpose: PyYAML is not a dependency of this project, so a
malformed workflow would not be caught by a schema check here.
"""
import pathlib
import re
import unittest
from pathlib import Path

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "TV-Spain.yml"
README = REPO_ROOT / "README.md"
REMOVED_GATE = REPO_ROOT / "scripts" / "madrid_noon_gate.py"


def workflow_text():
    return WORKFLOW.read_text(encoding="utf-8")


def readme_text():
    return README.read_text(encoding="utf-8")


def advertised_hours(text):
    """Return the UTC hours a document claims the daily run is scheduled for.

    Only the phrases that assert the current schedule are matched. The README also
    quotes the three historical slots when explaining the delay measurements, and
    those are measurements rather than promises: a bare "16:00 UTC" there must not
    be mistaken for a stale schedule. It likewise quotes the 48-hour EPG slot,
    which belongs to a different workflow.

    The README is written in Spanish, so the lead-ins have to recognise it; the
    English ones are kept so an older checkout still resolves.
    """
    lead_ins = (
        r"(?:scheduled for|one cron at|cron sits at|moved \d+ h earlier to"
        r"|programada para(?: las)?|adelant[oó] \d+ h hasta las"
        r"|cron est[áa] a las|cron a las)"
    )
    pattern = lead_ins + r" \*?\*?(\d{1,2}):00 UTC"
    return {int(h) for h in re.findall(pattern, text)}


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

    def test_single_cron_at_eight_utc(self):
        self.assertEqual(cron_entries(), ["0 8 * * *"])

    def test_cron_is_expressed_in_utc(self):
        # GitHub cron has no timezone field; a non-zero hour would silently move
        # the run away from the chosen slot.
        self.assertEqual(cron_entries()[0].split()[1], "8")

    def test_cron_is_daily_at_the_top_of_the_hour(self):
        fields = cron_entries()[0].split()
        self.assertEqual(fields[0], "0", "must fire at :00 so the delay stays measurable")
        self.assertEqual(fields[2:], ["*", "*", "*"])

    def test_logged_schedule_matches_the_cron(self):
        # The banner must not keep advertising the old slot: it is what a reader
        # checks to work out when the run was supposed to start.
        self.assertIn("Scheduled for 08:00 UTC", workflow_text())
        self.assertNotIn("Scheduled for 16:00 UTC", workflow_text())

    def test_readme_advertises_the_scheduled_slot(self):
        # Moving the cron leaves the hour advertised in the README behind by
        # default, and that is the only place a reader learns when the lists
        # refresh. Every hour the README calls the schedule must be the hour the
        # cron really uses.
        hour = int(cron_entries()[0].split()[1])
        advertised = advertised_hours(readme_text())
        self.assertNotEqual(
            advertised,
            set(),
            "README no longer says when the daily run is scheduled; "
            "test_advertised_hours_ignores_history must be kept in sync with it",
        )
        stale = advertised - {hour}
        self.assertEqual(
            stale,
            set(),
            f"README still advertises {sorted(stale)} UTC as the daily slot, "
            f"but the cron runs at {hour}:00 UTC",
        )

    def test_advertised_hours_ignores_history(self):
        # The check above would be worthless if it simply matched every `HH:00 UTC`
        # in the README, because the delay statistics legitimately quote all three
        # historical slots. Assert those quotes stay outside the result.
        self.assertEqual(advertised_hours("median delay 171 min at 00:00 UTC"), set())
        self.assertEqual(advertised_hours("103 min at 16:00 UTC"), set())
        self.assertEqual(advertised_hours("**16:00 UTC** was least congested"), set())
        self.assertEqual(advertised_hours("scheduled for **08:00 UTC**"), {8})
        self.assertEqual(advertised_hours("one cron at 08:00 UTC"), {8})
        # The Spanish phrasing the README actually uses.
        self.assertEqual(
            advertised_hours("retraso mediano de 171 min a las 00:00 UTC"), set()
        )
        self.assertEqual(advertised_hours("103 min a las 16:00 UTC"), set())
        self.assertEqual(
            advertised_hours("**16:00 UTC** fue la franja menos saturada"), set()
        )
        # The 48-hour EPG slot belongs to another workflow, not the daily one.
        self.assertEqual(advertised_hours("cada 48 horas a las 08:00 UTC"), set())
        self.assertEqual(advertised_hours("programada para **08:00 UTC**"), {8})
        self.assertEqual(advertised_hours("programada para las 08:00 UTC"), {8})
        self.assertEqual(advertised_hours("un único cron a las 08:00 UTC"), {8})

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
