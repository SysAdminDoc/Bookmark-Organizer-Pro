"""R-133: reversible actions run immediately instead of asking first.

The product rule is immediate action plus a toast, with an undo or safepoint
behind anything destructive. These cases pin the two halves of that: the
confirmations that were removed stay removed, and the undo each removal now
relies on actually restores what was deleted.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from bookmark_organizer_pro.core import CategoryManager
from bookmark_organizer_pro.managers import BookmarkManager, TagManager
from bookmark_organizer_pro.services.organization_rules import (
    OrganizationRule,
    OrganizationRulesService,
)

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "bookmark_organizer_pro"

# Every confirmation left in the product, with the reason it earns a modal.
# A prompt guarding an action the user can undo does not belong here.
JUSTIFIED_CONFIRMATIONS = {
    ("app_mixins/ai_settings.py", "downloads and executes an installer on this machine"),
    ("app_mixins/tools.py", "sends domain names to a third-party proxy, which cannot be recalled"),
    ("ui/management_dialogs.py", "rotating and revoking a credential break live secrets at once"),
}


def test_only_irreversible_actions_still_confirm():
    found = set()
    for source in sorted(PACKAGE.rglob("*.py")):
        relative = source.relative_to(PACKAGE).as_posix()
        for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            if "messagebox.ask" in line:
                found.add((relative, number))

    files = {relative for relative, _ in found}
    assert files == {name for name, _ in JUSTIFIED_CONFIRMATIONS}, (
        "a confirmation appeared in a file that has none justified, or a "
        f"justified one disappeared: {sorted(files)}"
    )
    # management_dialogs holds two (rotate and revoke); the others hold one each.
    assert len(found) == 4, sorted(found)


def test_no_import_or_rule_flow_blocks_on_a_confirmation():
    """These four flows all have a rollback safepoint or an undo behind them."""
    for name in (
        "app_mixins/import_export.py",
        "ui/highlights_workspace.py",
        "ui/organization_rules.py",
    ):
        text = (PACKAGE / name).read_text(encoding="utf-8")
        assert "messagebox.ask" not in text, f"{name} blocks on a confirmation again"


def test_deleting_a_rule_is_immediate_and_restorable(tmp_path, monkeypatch):
    """The Delete button no longer asks, so Restore has to work."""
    monkeypatch.setattr(
        OrganizationRulesService, "RULES_FILE", tmp_path / "organization_rules.json"
    )
    monkeypatch.setattr(
        OrganizationRulesService, "LEGACY_RULES_FILE", tmp_path / "smart_tag_rules.json"
    )
    manager = BookmarkManager(
        CategoryManager(filepath=tmp_path / "categories.json"),
        TagManager(filepath=tmp_path / "tags.json"),
        filepath=tmp_path / "bookmarks.json",
    )
    service = OrganizationRulesService(manager)

    rule = OrganizationRule.from_dict(
        {
            "name": "Docs to Reference",
            "conditions": [{"field": "domain", "operator": "equals", "value": "docs.python.org"}],
            "actions": [{"action": "set_category", "value": "Reference"}],
        }
    )
    service.add_rule(rule)
    stored = service.list_rules()[0]

    assert service.remove_rule(stored.rule_id) is True
    assert service.list_rules() == []

    # This is exactly what `_restore_rule` does with the rule it held on to.
    service.add_rule(stored)
    restored = service.list_rules()
    assert len(restored) == 1
    assert restored[0].rule_id == stored.rule_id
    assert restored[0].name == stored.name
    assert restored[0].to_dict() == stored.to_dict()


def test_the_rules_dialog_wires_delete_restore_and_the_import_mode():
    """The Restore button and the replace-on-import control have to exist, or
    removing the modals just removed the choice."""
    source = (PACKAGE / "ui/organization_rules.py").read_text(encoding="utf-8")

    assert "self.restore_button = self._button(rule_toolbar, _(\"Restore\")" in source
    assert "def _restore_rule(self)" in source
    assert "self._deleted_rule" in source
    assert "self.replace_on_import_var" in source
    assert "replace=replace" in source

    # Restore starts unavailable and is enabled by a delete.
    enable = re.search(r"def _delete_rule\(self\):(.*?)def _restore_rule", source, re.S)
    assert enable and 'self.restore_button.set_state("normal")' in enable.group(1)


def test_the_import_preflight_reports_instead_of_asking():
    source = (PACKAGE / "app_mixins/import_export.py").read_text(encoding="utf-8")
    assert "_confirm_import_preflight" not in source
    assert "def _report_import_preflight(self, label, preflight) -> None:" in source
    # The result summary is where the rollback lives, so it has to stay.
    assert "_show_import_result_summary" in source
    assert 'text=_("Roll Back")' in source


def test_deleted_highlights_report_that_undo_is_available():
    source = (PACKAGE / "ui/highlights_workspace.py").read_text(encoding="utf-8")
    assert "Deleted {count}. Undo is available." in source
    assert "def _undo_delete(self)" in source


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
