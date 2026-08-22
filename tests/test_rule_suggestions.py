"""Rule suggestions derived from how a library is already filed."""

from __future__ import annotations

import unittest

from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.rule_suggestions import (
    RuleSuggestion,
    existing_rule_domains,
    shipped_pattern_domains,
    suggest_domain_category_rules,
)


def _bookmark(index, url, category=""):
    return Bookmark(id=index, url=url, title=f"Bookmark {index}", category=category)


class TestRuleSuggestions(unittest.TestCase):
    def test_consistently_filed_host_becomes_a_proposal(self):
        bookmarks = [
            _bookmark(i, f"https://intranet.acme-corp.test/page{i}", "Work")
            for i in range(4)
        ]
        suggestions = suggest_domain_category_rules(bookmarks)

        self.assertEqual(len(suggestions), 1)
        proposal = suggestions[0]
        self.assertEqual(proposal.domain, "intranet.acme-corp.test")
        self.assertEqual(proposal.category, "Work")
        self.assertEqual(proposal.support, 4)
        self.assertEqual(proposal.agreement, 1.0)
        self.assertEqual(len(proposal.examples), 3)

    def test_thin_evidence_is_not_proposed(self):
        bookmarks = [_bookmark(i, f"https://rare.test/{i}", "Work") for i in range(2)]
        self.assertEqual(suggest_domain_category_rules(bookmarks), [])
        self.assertEqual(len(suggest_domain_category_rules(bookmarks, min_support=2)), 1)

    def test_a_host_filed_inconsistently_is_rejected(self):
        bookmarks = (
            [_bookmark(i, f"https://split.test/{i}", "Work") for i in range(3)]
            + [_bookmark(10 + i, f"https://split.test/x{i}", "Personal") for i in range(3)]
        )
        self.assertEqual(suggest_domain_category_rules(bookmarks), [])

    def test_dominant_category_still_wins_above_the_agreement_floor(self):
        bookmarks = (
            [_bookmark(i, f"https://mostly.test/{i}", "Reference") for i in range(9)]
            + [_bookmark(99, "https://mostly.test/odd", "Personal")]
        )
        suggestions = suggest_domain_category_rules(bookmarks)

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].category, "Reference")
        self.assertEqual(suggestions[0].competing, (("Personal", 1),))
        self.assertAlmostEqual(suggestions[0].agreement, 0.9)

    def test_placeholder_categories_are_not_decisions(self):
        for placeholder in ("", "Imported", "Uncategorized", "Uncategorized / Needs Review", "New folder"):
            with self.subTest(placeholder=placeholder):
                bookmarks = [
                    _bookmark(i, f"https://unfiled.test/{i}", placeholder) for i in range(5)
                ]
                self.assertEqual(suggest_domain_category_rules(bookmarks), [])

    def test_domains_the_shipped_patterns_already_route_are_skipped(self):
        bookmarks = [_bookmark(i, f"https://github.com/thing{i}", "Work") for i in range(5)]
        self.assertEqual(
            suggest_domain_category_rules(bookmarks, known_domains=shipped_pattern_domains()),
            [],
        )
        # Without that exclusion the same evidence does produce a proposal.
        self.assertEqual(len(suggest_domain_category_rules(bookmarks)), 1)

    def test_subdomains_of_shipped_patterns_are_skipped(self):
        """The pattern engine matches by suffix, so a rule for a subdomain of a
        shipped domain would change nothing."""
        from bookmark_organizer_pro.core.default_categories import DEFAULT_CATEGORIES
        from bookmark_organizer_pro.core.pattern_engine import PatternEngine

        engine = PatternEngine(DEFAULT_CATEGORIES)
        known = shipped_pattern_domains()
        for host in ("engineering.github.com", "careers.stackoverflow.com", "blog.python.org"):
            with self.subTest(host=host):
                self.assertIsNotNone(engine.match(f"https://{host}/x", ""))
                bookmarks = [_bookmark(i, f"https://{host}/p{i}", "My Own Folder") for i in range(4)]
                self.assertEqual(
                    suggest_domain_category_rules(bookmarks, known_domains=known), []
                )

    def test_long_hostnames_do_not_collide_after_name_truncation(self):
        from bookmark_organizer_pro.services.organization_rules import (
            MAX_NAME_LENGTH,
            OrganizationRule,
        )
        from bookmark_organizer_pro.services.rule_suggestions import _MAX_RULE_NAME

        self.assertEqual(_MAX_RULE_NAME, MAX_NAME_LENGTH)

        prefix = "a" * 63 + "." + "b" * 63
        bookmarks = []
        for index, tail in enumerate(("one.example", "two.example")):
            bookmarks += [
                _bookmark(index * 10 + i, f"https://{prefix}.{tail}/p{i}", "Cat")
                for i in range(3)
            ]
        suggestions = suggest_domain_category_rules(bookmarks)
        self.assertEqual(len(suggestions), 2)

        names = {OrganizationRule.from_dict(s.to_rule_document()).name for s in suggestions}
        self.assertEqual(len(names), 2, f"names collided after truncation: {names}")

    def test_domains_already_covered_by_a_saved_rule_are_skipped(self):
        bookmarks = [_bookmark(i, f"https://covered.test/{i}", "Work") for i in range(5)]
        self.assertEqual(
            suggest_domain_category_rules(bookmarks, existing_rule_domains=["covered.test"]),
            [],
        )

    def test_www_prefix_does_not_split_a_host(self):
        bookmarks = (
            [_bookmark(i, f"https://www.mixed.test/{i}", "Work") for i in range(2)]
            + [_bookmark(10 + i, f"https://mixed.test/x{i}", "Work") for i in range(2)]
        )
        suggestions = suggest_domain_category_rules(bookmarks)

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].domain, "mixed.test")
        self.assertEqual(suggestions[0].support, 4)

    def test_proposal_converts_to_a_valid_organization_rule(self):
        from bookmark_organizer_pro.services.organization_rules import OrganizationRule

        proposal = RuleSuggestion(
            domain="intranet.acme-corp.test", category="Work",
            support=4, total=4, agreement=1.0,
        )
        rule = OrganizationRule.from_dict(proposal.to_rule_document())

        self.assertEqual(rule.conditions[0]["field"], "domain")
        self.assertEqual(rule.conditions[0]["value"], "intranet.acme-corp.test")
        self.assertEqual(rule.actions[0], {"action": "set_category", "value": "Work"})

    def test_existing_rule_domains_reads_saved_rules(self):
        from bookmark_organizer_pro.services.organization_rules import OrganizationRule

        rule = OrganizationRule.from_dict({
            "name": "keep",
            "conditions": [{"field": "domain", "operator": "equals", "value": "WWW.Kept.test"}],
            "actions": [{"action": "set_category", "value": "Work"}],
        })
        self.assertEqual(existing_rule_domains([rule]), ["kept.test"])

    def test_strongest_evidence_is_listed_first(self):
        bookmarks = (
            [_bookmark(i, f"https://small.test/{i}", "Work") for i in range(3)]
            + [_bookmark(20 + i, f"https://big.test/{i}", "Work") for i in range(8)]
        )
        suggestions = suggest_domain_category_rules(bookmarks)

        self.assertEqual([s.domain for s in suggestions], ["big.test", "small.test"])


if __name__ == "__main__":
    unittest.main()
