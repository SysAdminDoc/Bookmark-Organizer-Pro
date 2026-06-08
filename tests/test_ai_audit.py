"""Tests for the AI audit log's default-improvement learning pipeline."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bookmark_organizer_pro.services import ai_audit_log as aal

UNCAT = aal.UNCATEGORIZED


def _entry(domain, ai_cat, conf, pred):
    return {
        "timestamp": "2026-06-08T00:00:00",
        "action": "categorize",
        "url": f"https://{domain}/x",
        "evaluation": {
            "domain": domain,
            "pattern_prediction": pred,
            "pattern_matched": bool(pred and pred != UNCAT),
            "ai_category": ai_cat,
            "ai_confidence": conf,
            "agreement": aal._classify_agreement(pred, ai_cat, conf),
        },
    }


class TestClassifyAgreement(unittest.TestCase):
    def test_buckets(self):
        c = aal._classify_agreement
        self.assertEqual(c(UNCAT, "Development", 0.9), "miss")
        self.assertEqual(c("", "Development", 0.9), "miss")
        self.assertEqual(c("Development", "Development", 0.9), "confirm")
        self.assertEqual(c("News", "Development", 0.9), "disagree")
        self.assertEqual(c("News", "Development", 0.3), "low_confidence")
        self.assertEqual(c("News", "", 0.9), "low_confidence")


class TestAnalyzeForDefaultImprovements(unittest.TestCase):
    def test_classifies_domains_into_add_review_confirm(self):
        entries = []
        # Defaults missed github entirely; AI confidently says Development x3 -> ADD
        entries += [_entry("github.com", "Development", 0.95, UNCAT) for _ in range(3)]
        # Default says Technology but AI says News x2 -> REVIEW (disagree)
        entries += [_entry("news.ycombinator.com", "News", 0.9, "Technology") for _ in range(2)]
        # Default already Social and AI agrees x2 -> CONFIRMED
        entries += [_entry("reddit.com", "Social", 0.9, "Social") for _ in range(2)]
        # Below confidence threshold -> ignored
        entries += [_entry("lowconf.com", "Whatever", 0.4, UNCAT) for _ in range(3)]
        # Below support threshold (only 1 sample) -> ignored
        entries += [_entry("singleton.com", "Finance", 0.9, UNCAT)]

        tmp = Path(tempfile.mkdtemp()) / "ai_audit.jsonl"
        tmp.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")

        with patch.object(aal, "AI_AUDIT_FILE", tmp):
            report = aal.analyze_for_default_improvements(min_confidence=0.7, min_support=2)

        self.assertEqual(report["summary"]["add_patterns"], 1)
        self.assertEqual(report["summary"]["review_patterns"], 1)
        self.assertEqual(report["summary"]["confirmed"], 1)

        add = report["add_patterns"][0]
        self.assertEqual(add["domain"], "github.com")
        self.assertEqual(add["suggested_category"], "Development")
        self.assertEqual(add["support"], 3)
        self.assertEqual(add["suggested_pattern"], "domain:github.com")

        review = report["review_patterns"][0]
        self.assertEqual(review["domain"], "news.ycombinator.com")
        self.assertEqual(review["current_default"], "Technology")
        self.assertEqual(review["suggested_category"], "News")

        # singleton/lowconf excluded
        domains = {r["domain"] for bucket in ("add_patterns", "review_patterns", "confirmed")
                   for r in report[bucket]}
        self.assertNotIn("lowconf.com", domains)
        self.assertNotIn("singleton.com", domains)

    def test_empty_log_is_safe(self):
        tmp = Path(tempfile.mkdtemp()) / "empty.jsonl"
        with patch.object(aal, "AI_AUDIT_FILE", tmp):
            report = aal.analyze_for_default_improvements()
        self.assertEqual(report["summary"]["add_patterns"], 0)
        self.assertEqual(report["unique_domains"], 0)


if __name__ == "__main__":
    unittest.main()
