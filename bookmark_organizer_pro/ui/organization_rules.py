"""Desktop workspace for previewable organization rules."""

from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from bookmark_organizer_pro.i18n import _, format_message
from bookmark_organizer_pro.services.organization_rules import (
    ALLOWED_ACTIONS,
    ALLOWED_FIELDS,
    ALLOWED_OPERATORS,
    OrganizationPreview,
    OrganizationRule,
    OrganizationRulesService,
)

from .foundation import FONTS
from .widget_controls import ModernButton
from .window_geometry import apply_screen_aware_geometry
from .widgets import apply_window_chrome, get_theme


def _compact(value, limit: int = 70) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: max(1, limit - 1)].rstrip() + "…"


def _condition_summary(rule: OrganizationRule) -> str:
    return " AND ".join(
        f"{condition['field']} {condition['operator']} {condition.get('value') or ''}".strip()
        for condition in rule.conditions
    )


def _action_summary(rule: OrganizationRule) -> str:
    return ", ".join(
        f"{action['action']}={action.get('value')}" for action in rule.actions
    )


class OrganizationRuleEditorDialog(tk.Toplevel):
    """Small editor that only emits schema-valid rule objects."""

    def __init__(self, parent, *, on_save, rule: OrganizationRule | None = None):
        theme = get_theme()
        super().__init__(parent)
        self.on_save = on_save
        self.rule = rule
        self.title(_("Organization rule"))
        apply_screen_aware_geometry(self, 860, 650)
        self.minsize(700, 500)
        self.configure(bg=theme.bg_primary)
        self.transient(parent)
        apply_window_chrome(self)
        self._condition_rows = []
        self._action_rows = []
        self._build()
        self._load_rule(rule)
        self.bind("<Escape>", lambda _event: self.destroy())
        self.grab_set()

    def _build(self) -> None:
        theme = get_theme()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)
        header = tk.Frame(self, bg=theme.bg_secondary, padx=18, pady=12)
        header.grid(row=0, column=0, sticky="ew")
        tk.Label(
            header, text=_("Define organization rule"), bg=theme.bg_secondary,
            fg=theme.text_primary, font=FONTS.header(bold=True), anchor="w",
        ).pack(fill=tk.X)
        tk.Label(
            header,
            text=_("Rules use allowlisted fields and actions. Preview before applying changes."),
            bg=theme.bg_secondary, fg=theme.text_secondary, font=FONTS.small(), anchor="w",
        ).pack(fill=tk.X, pady=(3, 0))

        details = tk.Frame(self, bg=theme.bg_primary, padx=18, pady=12)
        details.grid(row=1, column=0, sticky="ew")
        details.grid_columnconfigure(1, weight=1)
        tk.Label(details, text=_("Name"), bg=theme.bg_primary, fg=theme.text_muted, font=FONTS.small()).grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=4,
        )
        self.name_var = tk.StringVar()
        self.name_entry = ttk.Entry(details, textvariable=self.name_var)
        self.name_entry.grid(row=0, column=1, sticky="ew", pady=4)
        self.enabled_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(details, text=_("Enabled"), variable=self.enabled_var).grid(
            row=0, column=2, sticky="e", padx=(12, 0), pady=4,
        )

        self._section_label(details, 1, _("Conditions — all must match"))
        self.conditions_frame = tk.Frame(details, bg=theme.bg_primary)
        self.conditions_frame.grid(row=2, column=0, columnspan=3, sticky="ew")
        self.conditions_frame.grid_columnconfigure(1, weight=1)
        ModernButton(
            details, text=_("Add condition"), command=self._add_condition,
            padx=9, pady=5,
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(5, 10))

        self._section_label(details, 4, _("Actions — applied as one batch"))
        self.actions_frame = tk.Frame(details, bg=theme.bg_primary)
        self.actions_frame.grid(row=5, column=0, columnspan=3, sticky="ew")
        self.actions_frame.grid_columnconfigure(1, weight=1)
        ModernButton(
            details, text=_("Add action"), command=self._add_action,
            padx=9, pady=5,
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(5, 0))

        preview_hint = tk.Label(
            self, text=_("Use Preview in the workspace to inspect affected bookmarks and conflicts."),
            bg=theme.bg_primary, fg=theme.text_secondary, font=FONTS.small(), anchor="w",
        )
        preview_hint.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 8))

        self.error_label = tk.Label(
            self, text="", bg=theme.bg_primary, fg=theme.accent_error,
            font=FONTS.small(), anchor="w", justify=tk.LEFT,
        )
        self.error_label.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 6))

        spacer = tk.Frame(self, bg=theme.bg_primary)
        spacer.grid(row=4, column=0, sticky="nsew", padx=18)

        footer = tk.Frame(self, bg=theme.bg_secondary, padx=18, pady=10)
        footer.grid(row=5, column=0, sticky="ew")
        ModernButton(footer, text=_("Cancel"), command=self.destroy, padx=12, pady=6).pack(side=tk.RIGHT, padx=(8, 0))
        save_button = ModernButton(
            footer, text=_("Save rule"), command=self._save, style="primary", padx=12, pady=6,
        )
        save_button.pack(side=tk.RIGHT)

    @staticmethod
    def _section_label(parent, row: int, text: str) -> None:
        theme = get_theme()
        tk.Label(
            parent, text=text, bg=theme.bg_primary, fg=theme.text_primary,
            font=FONTS.small(bold=True), anchor="w",
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(8, 4))

    def _load_rule(self, rule: OrganizationRule | None) -> None:
        if rule is None:
            self.name_var.set("")
            self._add_condition()
            self._add_action()
            self.name_entry.focus_set()
            return
        self.name_var.set(rule.name)
        self.enabled_var.set(rule.enabled)
        for condition in rule.conditions:
            self._add_condition(condition)
        for action in rule.actions:
            self._add_action(action)

    def _add_condition(self, condition=None) -> None:
        theme = get_theme()
        row = tk.Frame(self.conditions_frame, bg=theme.bg_primary)
        row.pack(fill=tk.X, pady=2)
        field_var = tk.StringVar(value=(condition or {}).get("field", "domain"))
        operator_var = tk.StringVar(value=(condition or {}).get("operator", "contains"))
        value_var = tk.StringVar(value=(condition or {}).get("value", ""))
        field_combo = ttk.Combobox(row, textvariable=field_var, state="readonly", width=16, values=sorted(ALLOWED_FIELDS))
        field_combo.pack(side=tk.LEFT, padx=(0, 6))
        operator_combo = ttk.Combobox(row, textvariable=operator_var, state="readonly", width=14, values=sorted(ALLOWED_OPERATORS))
        operator_combo.pack(side=tk.LEFT, padx=(0, 6))
        value_entry = ttk.Entry(row, textvariable=value_var)
        value_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        remove = ModernButton(row, text=_("Remove"), command=lambda: self._remove_row(self._condition_rows, row), padx=7, pady=4)
        remove.pack(side=tk.LEFT)
        item = {"frame": row, "field": field_var, "operator": operator_var, "value": value_var, "entry": value_entry}
        self._condition_rows.append(item)
        operator_combo.bind("<<ComboboxSelected>>", lambda _event, item=item: self._sync_condition_value(item))
        self._sync_condition_value(item)

    def _add_action(self, action=None) -> None:
        row = tk.Frame(self.actions_frame, bg=get_theme().bg_primary)
        row.pack(fill=tk.X, pady=2)
        action_var = tk.StringVar(value=(action or {}).get("action", "add_tag"))
        value = (action or {}).get("value", "")
        value_var = tk.StringVar(value=str(value).lower() if isinstance(value, bool) else str(value))
        action_combo = ttk.Combobox(row, textvariable=action_var, state="readonly", width=20, values=sorted(ALLOWED_ACTIONS))
        action_combo.pack(side=tk.LEFT, padx=(0, 6))
        value_entry = ttk.Entry(row, textvariable=value_var)
        value_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        remove = ModernButton(row, text=_("Remove"), command=lambda: self._remove_row(self._action_rows, row), padx=7, pady=4)
        remove.pack(side=tk.LEFT)
        item = {"frame": row, "action": action_var, "value": value_var, "entry": value_entry}
        self._action_rows.append(item)
        action_combo.bind("<<ComboboxSelected>>", lambda _event, item=item: self._sync_action_value(item))
        self._sync_action_value(item)

    @staticmethod
    def _remove_row(rows, frame) -> None:
        if len(rows) <= 1:
            return
        rows[:] = [item for item in rows if item["frame"] is not frame]
        frame.destroy()

    @staticmethod
    def _sync_condition_value(item) -> None:
        boolean_operator = item["operator"].get() in {"is_true", "is_false"}
        item["entry"].configure(state="disabled" if boolean_operator else "normal")
        if boolean_operator:
            item["value"].set("")

    @staticmethod
    def _sync_action_value(item) -> None:
        action = item["action"].get()
        if action in {"set_read_later", "set_pinned", "set_archived"}:
            if item["value"].get() not in {"true", "false"}:
                item["value"].set("true")
        else:
            item["entry"].configure(state="normal")

    def _save(self) -> None:
        try:
            conditions = tuple(
                {
                    "field": item["field"].get(),
                    "operator": item["operator"].get(),
                    "value": item["value"].get(),
                }
                for item in self._condition_rows
            )
            actions = tuple(
                {"action": item["action"].get(), "value": item["value"].get()}
                for item in self._action_rows
            )
            rule = OrganizationRule(
                name=self.name_var.get(),
                conditions=conditions,
                actions=actions,
                enabled=self.enabled_var.get(),
                rule_id=self.rule.rule_id if self.rule else "",
                created_at=self.rule.created_at if self.rule else "",
            )
        except ValueError as exc:
            self.error_label.configure(text=str(exc))
            return
        try:
            self.on_save(rule)
        except (OSError, ValueError) as exc:
            self.error_label.configure(text=str(exc))
            return
        self.destroy()


class OrganizationRulesDialog(tk.Toplevel):
    """Inspect, preview, apply, undo, import, and export organization rules."""

    def __init__(self, parent, bookmark_manager):
        theme = get_theme()
        super().__init__(parent)
        self.bookmark_manager = bookmark_manager
        self.service = OrganizationRulesService(bookmark_manager)
        self.preview: OrganizationPreview | None = None
        self.title(_("Organization rules"))
        apply_screen_aware_geometry(self, 1120, 760)
        self.minsize(860, 600)
        self.configure(bg=theme.bg_primary)
        self.transient(parent)
        apply_window_chrome(self)
        self._build()
        self._refresh_rules()
        self.bind("<Escape>", lambda _event: self.destroy())
        self.bind("<Return>", self._on_return)
        self.bind("<Delete>", lambda _event: self._delete_rule() or "break")

    def _build(self) -> None:
        theme = get_theme()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=1)
        header = tk.Frame(self, bg=theme.bg_secondary, padx=18, pady=12)
        header.grid(row=0, column=0, sticky="ew")
        copy_frame = tk.Frame(header, bg=theme.bg_secondary)
        copy_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(copy_frame, text=_("Organization rules"), bg=theme.bg_secondary, fg=theme.text_primary, font=FONTS.header(bold=True), anchor="w").pack(fill=tk.X)
        tk.Label(
            copy_frame,
            text=_("Preview deterministic, allowlisted changes before one atomic batch."),
            bg=theme.bg_secondary, fg=theme.text_secondary, font=FONTS.small(), anchor="w",
        ).pack(fill=tk.X, pady=(3, 0))
        self.status = tk.Label(header, text="", bg=theme.bg_secondary, fg=theme.text_muted, font=FONTS.small(), anchor="e")
        self.status.pack(side=tk.RIGHT, padx=(12, 0))

        rule_frame = tk.Frame(self, bg=theme.bg_primary, padx=18, pady=10)
        rule_frame.grid(row=1, column=0, sticky="nsew")
        rule_frame.grid_rowconfigure(1, weight=1)
        rule_frame.grid_columnconfigure(0, weight=1)
        rule_toolbar = tk.Frame(rule_frame, bg=theme.bg_primary)
        rule_toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self._button(rule_toolbar, _("New"), self._new_rule, "primary")
        self.edit_button = self._button(rule_toolbar, _("Edit"), self._edit_rule)
        self.delete_button = self._button(rule_toolbar, _("Delete"), self._delete_rule, "danger")
        self.enable_button = self._button(rule_toolbar, _("Enable"), lambda: self._set_enabled(True))
        self.disable_button = self._button(rule_toolbar, _("Disable"), lambda: self._set_enabled(False))
        self._button(rule_toolbar, _("Import"), self._import_rules)
        self._button(rule_toolbar, _("Export"), self._export_rules)
        self.rules_tree = ttk.Treeview(rule_frame, columns=("enabled", "name", "conditions", "actions"), show="headings", selectmode="browse", height=7)
        for column, label, width in (
            ("enabled", _("Enabled"), 100), ("name", _("Name"), 190),
            ("conditions", _("Conditions"), 430), ("actions", _("Actions"), 330),
        ):
            self.rules_tree.heading(column, text=label)
            self.rules_tree.column(column, width=width, minwidth=70, stretch=column in {"conditions", "actions"})
        self.rules_tree.grid(row=1, column=0, sticky="nsew")
        rules_scroll = ttk.Scrollbar(rule_frame, orient=tk.VERTICAL, command=self.rules_tree.yview)
        rules_scroll.grid(row=1, column=1, sticky="ns")
        self.rules_tree.configure(yscrollcommand=rules_scroll.set)
        self.rules_tree.bind("<<TreeviewSelect>>", lambda _event: self._sync_rule_actions())
        self.rules_tree.bind("<Double-1>", lambda _event: self._edit_rule())

        preview_frame = tk.Frame(self, bg=theme.bg_primary, padx=18, pady=0)
        preview_frame.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        preview_frame.grid_rowconfigure(1, weight=1)
        preview_frame.grid_columnconfigure(0, weight=1)
        tk.Label(preview_frame, text=_("Latest preview"), bg=theme.bg_primary, fg=theme.text_primary, font=FONTS.small(bold=True), anchor="w").grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.preview_tree = ttk.Treeview(preview_frame, columns=("bookmark", "rules", "changes", "conflicts"), show="headings", selectmode="browse", height=6)
        for column, label, width in (
            ("bookmark", _("Bookmark"), 230), ("rules", _("Matched rules"), 260),
            ("changes", _("Changes"), 390), ("conflicts", _("Conflicts"), 180),
        ):
            self.preview_tree.heading(column, text=label)
            self.preview_tree.column(column, width=width, minwidth=70, stretch=column in {"rules", "changes"})
        self.preview_tree.grid(row=1, column=0, sticky="nsew")
        preview_scroll = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=self.preview_tree.yview)
        preview_scroll.grid(row=1, column=1, sticky="ns")
        self.preview_tree.configure(yscrollcommand=preview_scroll.set)

        footer = tk.Frame(self, bg=theme.bg_secondary, padx=18, pady=10)
        footer.grid(row=3, column=0, sticky="ew")
        self.preview_status = tk.Label(footer, text=_("Run Preview to inspect the next batch."), bg=theme.bg_secondary, fg=theme.text_secondary, font=FONTS.small(), anchor="w")
        self.preview_status.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.undo_button = ModernButton(footer, text=_("Undo last"), command=self._undo_last, state="disabled", padx=10, pady=6)
        self.undo_button.pack(side=tk.RIGHT, padx=(8, 0))
        self.apply_button = ModernButton(footer, text=_("Apply preview"), command=self._apply_preview, style="success", state="disabled", padx=10, pady=6)
        self.apply_button.pack(side=tk.RIGHT, padx=(8, 0))
        ModernButton(footer, text=_("Preview"), command=self._preview_rules, style="primary", padx=10, pady=6).pack(side=tk.RIGHT)
        ModernButton(footer, text=_("Suggest from library"), command=self._suggest_rules, padx=10, pady=6).pack(side=tk.RIGHT, padx=(0, 8))

    def _suggest_rules(self) -> None:
        """Propose rules for hosts this library already files consistently."""
        from tkinter import messagebox
        from bookmark_organizer_pro.services.rule_suggestions import (
            existing_rule_domains,
            shipped_pattern_domains,
            suggest_domain_category_rules,
        )

        suggestions = suggest_domain_category_rules(
            self.bookmark_manager.get_all_bookmarks(),
            known_domains=shipped_pattern_domains(),
            existing_rule_domains=existing_rule_domains(self.service.list_rules()),
        )
        if not suggestions:
            messagebox.showinfo(
                _("Suggest rules"),
                _("No host is filed consistently enough to turn into a rule yet."),
                parent=self,
            )
            return

        shown = suggestions[:12]
        lines = [
            format_message(
                "{domain} to {category} ({support} of {total} agree)",
                domain=item.domain, category=item.category,
                support=item.support, total=item.total,
            )
            for item in shown
        ]
        if len(suggestions) > len(shown):
            lines.append(format_message("and {count} more", count=len(suggestions) - len(shown)))
        lines.append("")
        lines.append(_("Save these rules? Nothing is applied until you run Preview."))

        if not messagebox.askyesno(_("Suggest rules"), "\n".join(lines), parent=self):
            return
        for item in suggestions:
            self.service.add_rule(item.to_rule_document())
        self._refresh_rules()
        self.preview_status.configure(
            text=format_message("Saved {count} suggested rule(s). Run Preview to inspect them.",
                                count=len(suggestions))
        )

    @staticmethod
    def _button(parent, text, command, style="default"):
        button = ModernButton(parent, text=text, command=command, style=style, padx=9, pady=5)
        button.pack(side=tk.LEFT, padx=(0, 6))
        return button

    def _refresh_rules(self) -> None:
        for item in self.rules_tree.get_children():
            self.rules_tree.delete(item)
        for rule in self.service.list_rules():
            self.rules_tree.insert(
                "", tk.END, iid=rule.rule_id,
                values=(
                    _("Yes") if rule.enabled else _("No"),
                    rule.name,
                    _compact(_condition_summary(rule), 86),
                    _compact(_action_summary(rule), 68),
                ),
            )
        self._sync_rule_actions()
        if self.service.load_errors:
            self.status.configure(text=_compact(self.service.load_errors[0], 100))
        elif self.service.last_run:
            self.status.configure(text=format_message("Last run: {status}", status=self.service.last_run.status))
        else:
            self.status.configure(text=format_message("{count} rule(s)", count=len(self.service.rules)))

    def _selected_rule(self) -> OrganizationRule | None:
        selection = self.rules_tree.selection()
        if not selection:
            return None
        rule_id = selection[0]
        return next((rule for rule in self.service.rules if rule.rule_id == rule_id), None)

    def _sync_rule_actions(self) -> None:
        selected = self._selected_rule()
        state = "normal" if selected else "disabled"
        for button in (self.edit_button, self.delete_button, self.enable_button, self.disable_button):
            button.set_state(state)

    def _new_rule(self) -> None:
        OrganizationRuleEditorDialog(self, on_save=self._save_rule)

    def _edit_rule(self) -> None:
        rule = self._selected_rule()
        if rule:
            OrganizationRuleEditorDialog(self, rule=rule, on_save=self._save_rule)

    def _save_rule(self, rule: OrganizationRule) -> None:
        self.service.add_rule(rule)
        self.preview = None
        self.apply_button.set_state("disabled")
        self._refresh_rules()
        self.preview_status.configure(text=format_message("Saved rule: {name}", name=rule.name))

    def _delete_rule(self):
        rule = self._selected_rule()
        if not rule:
            return "break"
        if not messagebox.askyesno(_("Delete rule"), format_message("Delete rule '{name}'?", name=rule.name), parent=self):
            return "break"
        self.service.remove_rule(rule.rule_id)
        self.preview = None
        self.apply_button.set_state("disabled")
        self._refresh_rules()
        return "break"

    def _set_enabled(self, enabled: bool) -> None:
        rule = self._selected_rule()
        if not rule:
            return
        self.service.set_enabled(rule.rule_id, enabled)
        self.preview = None
        self.apply_button.set_state("disabled")
        self._refresh_rules()

    def _preview_rules(self) -> None:
        self.preview = self.service.preview()
        for item in self.preview_tree.get_children():
            self.preview_tree.delete(item)
        changes_by_id = {}
        for change in self.preview.changes:
            changes_by_id.setdefault(change.bookmark_id, []).append(change)
        conflicts_by_id = {}
        for conflict in self.preview.conflicts:
            conflicts_by_id.setdefault(conflict.bookmark_id, []).append(conflict)
        for bookmark_id in sorted(set(changes_by_id) | set(conflicts_by_id)):
            bookmark = self.bookmark_manager.get_bookmark(bookmark_id)
            changes = changes_by_id.get(bookmark_id, [])
            conflicts = conflicts_by_id.get(bookmark_id, [])
            self.preview_tree.insert(
                "", tk.END, iid=str(bookmark_id),
                values=(
                    f"{bookmark_id} · {_compact(bookmark.title if bookmark else _('Missing bookmark'), 42)}",
                    _compact(", ".join(dict.fromkeys(name for change in changes for name in change.rule_names)), 44),
                    _compact("; ".join(f"{change.field}: {change.before} → {change.after}" for change in changes), 72),
                    _compact("; ".join(conflict.message for conflict in conflicts), 42),
                ),
            )
        self.preview_status.configure(
            text=format_message(
                "Preview: {affected} bookmark(s), {changes} change(s), {conflicts} conflict(s), {errors} error(s)",
                affected=self.preview.affected_count,
                changes=self.preview.change_count,
                conflicts=self.preview.conflict_count,
                errors=self.preview.error_count,
            )
        )
        self.apply_button.set_state("normal" if self.preview.changes else "disabled")

    def _apply_preview(self) -> None:
        if self.preview is None:
            self._preview_rules()
        if self.preview is None or not self.preview.changes:
            return
        if self.preview.conflicts and not messagebox.askyesno(
            _("Apply organization rules"),
            format_message("{count} conflict(s) will be skipped. Apply the remaining changes?", count=self.preview.conflict_count),
            parent=self,
        ):
            return
        report = self.service.apply(self.preview)
        self.preview = None
        self.apply_button.set_state("disabled")
        self.undo_button.set_state("normal" if report.undo_available else "disabled")
        self.preview_status.configure(text=format_message("Run {status}: {count} bookmark(s) changed.", status=report.status, count=report.affected_count))
        self._refresh_rules()

    def _undo_last(self) -> None:
        report = self.service.undo_last()
        self.undo_button.set_state("normal" if report.undo_available else "disabled")
        self.preview_status.configure(text=format_message("Undo {status}: {count} bookmark(s).", status=report.status, count=report.affected_count))
        self._refresh_rules()

    def _import_rules(self) -> None:
        path = filedialog.askopenfilename(parent=self, title=_("Import organization rules"), filetypes=[(_("JSON files"), "*.json"), (_("All files"), "*")])
        if not path:
            return
        replace = messagebox.askyesno(_("Replace rules"), _("Replace the current rules with this import? Choose No to merge."), parent=self)
        try:
            count = self.service.import_rules(path, replace=replace)
        except (OSError, ValueError) as exc:
            messagebox.showerror(_("Import failed"), str(exc), parent=self)
            return
        self.preview = None
        self.apply_button.set_state("disabled")
        self._refresh_rules()
        self.preview_status.configure(text=format_message("Imported {count} rule(s).", count=count))

    def _export_rules(self) -> None:
        path = filedialog.asksaveasfilename(parent=self, title=_("Export organization rules"), initialfile="organization-rules.json", defaultextension=".json", filetypes=[(_("JSON files"), "*.json")])
        if not path:
            return
        try:
            exported = self.service.export_rules(Path(path))
        except OSError as exc:
            messagebox.showerror(_("Export failed"), str(exc), parent=self)
            return
        self.preview_status.configure(text=format_message("Exported {name}", name=exported.name))

    def _on_return(self, _event=None):
        if self.rules_tree.focus():
            self._edit_rule()
        return "break"


__all__ = ["OrganizationRuleEditorDialog", "OrganizationRulesDialog"]
