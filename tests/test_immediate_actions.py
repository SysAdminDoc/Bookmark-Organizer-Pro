"""R-133: reversible actions run immediately instead of asking first.

The product rule is immediate action plus a toast, with an undo or safepoint
behind anything destructive. These cases pin the two halves of that: the
confirmations that were removed stay removed, and the undo each removal now
relies on actually restores what was deleted.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bookmark_organizer_pro.core import CategoryManager
from bookmark_organizer_pro.managers import BookmarkManager, TagManager
from unittest import mock

from bookmark_organizer_pro.services.organization_rules import (
    ORGANIZATION_RULES_SCHEMA,
    ORGANIZATION_RULES_VERSION,
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


class _StubButton:
    """The two state calls `_delete_rule` and `_restore_rule` make on a button."""

    def __init__(self):
        self.state = "disabled"
        self.focused = False

    def set_state(self, state):
        self.state = state

    def focus_set(self):
        self.focused = True


class _StubLabel:
    def __init__(self):
        self.text = ""

    def configure(self, **kwargs):
        self.text = kwargs.get("text", self.text)


def _dialog(service):
    """An OrganizationRulesDialog with only what the undo paths touch.

    Built without Tk on purpose: the standing rule is that GUI validation never
    takes over the screen, and these two methods are pure state machines over
    the service plus three widgets.
    """
    from bookmark_organizer_pro.ui.organization_rules import OrganizationRulesDialog

    dialog = OrganizationRulesDialog.__new__(OrganizationRulesDialog)
    dialog.service = service
    dialog._undo_stack = []
    dialog.restore_button = _StubButton()
    dialog.apply_button = _StubButton()
    dialog.preview_status = _StubLabel()
    dialog.preview = None
    dialog._refresh_rules = lambda: None
    dialog._selected_rule = lambda: None
    return dialog


def _rule(name, value="Reference"):
    return OrganizationRule.from_dict(
        {
            "name": name,
            "conditions": [{"field": "domain", "operator": "equals", "value": f"{name.lower()}.example"}],
            "actions": [{"action": "set_category", "value": value}],
        }
    )


def _service(tmp_path, monkeypatch):
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
    return OrganizationRulesService(manager)


def test_a_second_delete_does_not_throw_the_first_one_away(tmp_path, monkeypatch):
    """The undo was one slot, so deleting A then B lost A for good while the
    status line still said a restore was available."""
    service = _service(tmp_path, monkeypatch)
    for name in ("Alpha", "Beta", "Gamma"):
        service.add_rule(_rule(name))
    dialog = _dialog(service)

    for name in ("Alpha", "Beta"):
        target = next(r for r in service.list_rules() if r.name == name)
        dialog._selected_rule = lambda target=target: target
        dialog._delete_rule()

    assert [r.name for r in service.list_rules()] == ["Gamma"]
    dialog._restore_rule()
    dialog._restore_rule()
    # Both come back, and each lands where it was rather than on the end.
    assert [r.name for r in service.list_rules()] == ["Alpha", "Beta", "Gamma"]
    assert dialog.restore_button.state == "disabled"


def test_a_refused_restore_keeps_the_rule_it_could_not_put_back(tmp_path, monkeypatch):
    """The held rule used to be cleared before the service accepted it, so a
    restore refused at the rule ceiling threw the rule away for good."""
    service = _service(tmp_path, monkeypatch)
    service.add_rule(_rule("Alpha"))
    dialog = _dialog(service)
    dialog._selected_rule = lambda: service.list_rules()[0]
    dialog._delete_rule()

    errors = []
    with mock.patch(
        "bookmark_organizer_pro.ui.organization_rules.messagebox.showerror",
        side_effect=lambda *a, **k: errors.append(a),
    ), mock.patch.object(
        OrganizationRulesService, "restore_rules", side_effect=ValueError("no room")
    ):
        dialog._restore_rule()

    assert errors, "the user was not told the restore failed"
    assert dialog.restore_button.state == "normal"
    assert len(dialog._undo_stack) == 1

    dialog._restore_rule()
    assert [r.name for r in service.list_rules()] == ["Alpha"]


def test_restore_refuses_rather_than_overwriting_a_rule_that_took_the_name(
    tmp_path, monkeypatch
):
    """`add_rule` upserts on id **or** name, so undoing a delete through it
    could silently replace a different rule that had taken the name."""
    service = _service(tmp_path, monkeypatch)
    service.add_rule(_rule("Alpha", value="Reference"))
    dialog = _dialog(service)
    dialog._selected_rule = lambda: service.list_rules()[0]
    dialog._delete_rule()

    service.add_rule(_rule("Alpha", value="Development"))

    errors = []
    with mock.patch(
        "bookmark_organizer_pro.ui.organization_rules.messagebox.showerror",
        side_effect=lambda *a, **k: errors.append(a),
    ):
        dialog._restore_rule()

    assert errors, "the user was not told why nothing was restored"
    surviving = service.list_rules()
    assert len(surviving) == 1
    action = surviving[0].actions[0]
    value = action["value"] if isinstance(action, dict) else action.value
    assert value == "Development", "the newer rule was clobbered"


def test_a_replace_import_can_be_put_back(tmp_path, monkeypatch):
    """Replacing discards every rule at once and nothing else undoes that."""
    import json

    service = _service(tmp_path, monkeypatch)
    for name in ("Alpha", "Beta"):
        service.add_rule(_rule(name))
    before = [r.name for r in service.list_rules()]

    source = tmp_path / "incoming.json"
    source.write_text(
        json.dumps(
            {
                "schema": ORGANIZATION_RULES_SCHEMA,
                "schema_version": ORGANIZATION_RULES_VERSION,
                "rules": [_rule("Imported").to_dict()],
            }
        ),
        encoding="utf-8",
    )

    previous = service.list_rules()
    service.import_rules(source, replace=True)
    assert [r.name for r in service.list_rules()] == ["Imported"]

    dialog = _dialog(service)
    dialog._push_undo(("all", previous))
    dialog._restore_rule()
    assert [r.name for r in service.list_rules()] == before


def test_the_import_preflight_reports_instead_of_asking():
    source = (PACKAGE / "app_mixins/import_export.py").read_text(encoding="utf-8")
    assert "_confirm_import_preflight" not in source
    assert "def _report_import_preflight(self, label, preflight) -> None:" in source
    # The result summary is where the rollback lives, so it has to stay.
    assert "_show_import_result_summary" in source
    assert 'text=_("Roll Back")' in source


def test_highlight_deletes_stack_so_a_second_one_keeps_the_first():
    """Deleting is immediate now, so the undo has to survive a second delete.
    One slot meant batch two silently replaced batch one while the status line
    still said undo was available."""
    from bookmark_organizer_pro.ui.highlights_workspace import HighlightsWorkspaceDialog

    class _Workspace:
        def __init__(self):
            self.live = {"a", "b", "c", "d"}

        def delete_many(self, ids):
            removed = tuple(i for i in ids if i in self.live)
            self.live -= set(removed)
            return removed

        def restore_many(self, ids):
            self.live |= set(ids)
            return len(ids)

    dialog = HighlightsWorkspaceDialog.__new__(HighlightsWorkspaceDialog)
    dialog.workspace = _Workspace()
    dialog._deleted_batches = []
    dialog.page = None
    dialog.status = _StubLabel()
    dialog.undo_button = _StubButton()
    dialog._refresh = lambda **kwargs: None

    class _Record:
        def __init__(self, ident):
            self.id = ident

    dialog._selected_records = lambda: [_Record("a"), _Record("b")]
    dialog._delete_selected()
    dialog._selected_records = lambda: [_Record("c")]
    dialog._delete_selected()
    assert dialog.workspace.live == {"d"}
    assert len(dialog._deleted_batches) == 2

    dialog._undo_delete()
    assert dialog.workspace.live == {"c", "d"}
    assert "earlier batch can still be restored" in dialog.status.text
    dialog._undo_delete()
    assert dialog.workspace.live == {"a", "b", "c", "d"}
    assert dialog._deleted_batches == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
