"""Bounded, declarative organization rules with preview, apply, and undo.

This module deliberately has no expression evaluator or plugin hooks.  Rules
are data, predicates and actions are allowlisted, and every mutating run is
planned before it enters :class:`BookmarkManager.batch`.
"""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import regex

from bookmark_organizer_pro.constants import DATA_DIR
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.utils.runtime import atomic_json_write


ORGANIZATION_RULES_SCHEMA = "bookmark-organizer-pro/organization-rules"
ORGANIZATION_RULES_VERSION = 1
RULES_SCHEMA = ORGANIZATION_RULES_SCHEMA
RULES_VERSION = ORGANIZATION_RULES_VERSION

MAX_RULES = 200
MAX_CONDITIONS = 20
MAX_ACTIONS = 20
MAX_BOOKMARKS = 50_000
MAX_CHANGES = 100_000
MAX_ERRORS = 100
MAX_CONFLICTS = 100_000
MAX_NAME_LENGTH = 120
MAX_ID_LENGTH = 120
MAX_VALUE_LENGTH = 500
MAX_TAG_LENGTH = 120
MAX_CATEGORY_LENGTH = 240
MAX_IMPORT_BYTES = 2_000_000
REGEX_TIMEOUT_SECONDS = 0.02

ALLOWED_FIELDS = frozenset(
    {
        "domain",
        "title",
        "url",
        "category",
        "notes",
        "tag",
        "read_later",
        "pinned",
        "archived",
        "content_type",
    }
)
ALLOWED_OPERATORS = frozenset(
    {"contains", "starts_with", "ends_with", "equals", "not_equals", "regex", "is_true", "is_false"}
)
ALLOWED_ACTIONS = frozenset(
    {"add_tag", "remove_tag", "set_category", "set_read_later", "set_pinned", "set_archived"}
)
STRING_FIELDS = frozenset({"domain", "title", "url", "category", "notes", "tag", "content_type"})
BOOLEAN_FIELDS = frozenset({"read_later", "pinned", "archived"})
BOOLEAN_ACTIONS = frozenset({"set_read_later", "set_pinned", "set_archived"})


def _now() -> str:
    return datetime.now().isoformat()


def _text(value: Any, *, limit: int = MAX_VALUE_LENGTH) -> str:
    return str(value or "").strip()[:limit]


def _strict_bool(value: Any, *, label: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise ValueError(f"{label} must be true or false")


def _canonical_id(name: str) -> str:
    digest = hashlib.sha256(name.strip().casefold().encode("utf-8")).hexdigest()[:20]
    return f"rule_{digest}"


def _json_fingerprint(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalize_condition(raw: Mapping[str, Any]) -> Dict[str, str]:
    if not isinstance(raw, Mapping):
        raise ValueError("Each condition must be an object")
    unknown = set(raw) - {"field", "operator", "value"}
    if unknown:
        raise ValueError(f"Condition contains unsupported keys: {', '.join(sorted(unknown))}")
    field_name = _text(raw.get("field"), limit=40).lower()
    operator = _text(raw.get("operator"), limit=40).lower()
    if field_name not in ALLOWED_FIELDS:
        raise ValueError(f"Unsupported condition field: {field_name or '(empty)'}")
    if operator not in ALLOWED_OPERATORS:
        raise ValueError(f"Unsupported condition operator: {operator or '(empty)'}")
    if operator in {"is_true", "is_false"}:
        if field_name not in BOOLEAN_FIELDS:
            raise ValueError(f"{operator} is only valid for boolean fields")
        value = ""
    else:
        value = _text(raw.get("value"))
        if not value:
            raise ValueError("Condition value is required")
        if field_name in BOOLEAN_FIELDS:
            _strict_bool(value, label=f"Condition value for {field_name}")
        if operator == "regex":
            if len(value) > 250:
                raise ValueError("Regex conditions are limited to 250 characters")
            try:
                regex.compile(value)
            except regex.error as exc:
                raise ValueError(f"Invalid regex condition: {exc}") from exc
    return {"field": field_name, "operator": operator, "value": value}


def _normalize_action(raw: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError("Each action must be an object")
    unknown = set(raw) - {"action", "type", "value"}
    if unknown:
        raise ValueError(f"Action contains unsupported keys: {', '.join(sorted(unknown))}")
    action = _text(raw.get("action", raw.get("type")), limit=40).lower()
    if action not in ALLOWED_ACTIONS:
        raise ValueError(f"Unsupported organization action: {action or '(empty)'}")
    if action in {"add_tag", "remove_tag"}:
        value = _text(raw.get("value"), limit=MAX_TAG_LENGTH)
        if not value:
            raise ValueError(f"{action} requires a tag")
    elif action == "set_category":
        value = _text(raw.get("value"), limit=MAX_CATEGORY_LENGTH)
        if not value:
            raise ValueError("set_category requires a category")
    else:
        value = _strict_bool(raw.get("value"), label=f"{action} value")
    return {"action": action, "value": value}


@dataclass(frozen=True)
class OrganizationRule:
    """A validated rule made only from allowlisted predicates and actions."""

    name: str
    conditions: Tuple[Dict[str, str], ...]
    actions: Tuple[Dict[str, Any], ...]
    enabled: bool = True
    rule_id: str = ""
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        name = _text(self.name, limit=MAX_NAME_LENGTH)
        if not name:
            raise ValueError("Rule name is required")
        if len(self.conditions) == 0 or len(self.conditions) > MAX_CONDITIONS:
            raise ValueError(f"Rules require 1-{MAX_CONDITIONS} conditions")
        if len(self.actions) == 0 or len(self.actions) > MAX_ACTIONS:
            raise ValueError(f"Rules require 1-{MAX_ACTIONS} actions")
        normalized_conditions = tuple(_normalize_condition(condition) for condition in self.conditions)
        normalized_actions = tuple(_normalize_action(action) for action in self.actions)
        rule_id = _text(self.rule_id, limit=MAX_ID_LENGTH) or _canonical_id(name)
        if any(char.isspace() for char in rule_id):
            raise ValueError("Rule ID cannot contain whitespace")
        created_at = _text(self.created_at, limit=64) or _now()
        updated_at = _text(self.updated_at, limit=64) or created_at
        enabled = _strict_bool(self.enabled, label="Rule enabled")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "conditions", normalized_conditions)
        object.__setattr__(self, "actions", normalized_actions)
        object.__setattr__(self, "rule_id", rule_id)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "updated_at", updated_at)
        object.__setattr__(self, "enabled", enabled)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OrganizationRule":
        if not isinstance(data, Mapping):
            raise ValueError("Organization rule must be an object")
        unknown = set(data) - {
            "rule_id", "id", "name", "conditions", "actions", "enabled", "created_at", "updated_at",
        }
        if unknown:
            raise ValueError(f"Rule contains unsupported keys: {', '.join(sorted(unknown))}")
        conditions = data.get("conditions")
        actions = data.get("actions")
        if not isinstance(conditions, list):
            raise ValueError("Rule conditions must be a list")
        if not isinstance(actions, list):
            raise ValueError("Rule actions must be a list")
        return cls(
            name=data.get("name", ""),
            conditions=tuple(conditions),
            actions=tuple(actions),
            enabled=data.get("enabled", True),
            rule_id=data.get("rule_id", data.get("id", "")),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "conditions": [dict(condition) for condition in self.conditions],
            "actions": [dict(action) for action in self.actions],
            "enabled": self.enabled,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class OrganizationRuleChange:
    """One exact field transition in a preview or applied run."""

    bookmark_id: int
    field: str
    before: Any
    after: Any
    rule_ids: Tuple[str, ...] = ()
    rule_names: Tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bookmark_id": self.bookmark_id,
            "field": self.field,
            "before": copy.deepcopy(self.before),
            "after": copy.deepcopy(self.after),
            "rule_ids": list(self.rule_ids),
            "rule_names": list(self.rule_names),
        }


@dataclass(frozen=True)
class OrganizationRuleConflict:
    """A conflicting set of actions that was deliberately skipped."""

    bookmark_id: int
    field: str
    proposed_values: Tuple[Any, ...]
    rule_ids: Tuple[str, ...]
    rule_names: Tuple[str, ...]
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bookmark_id": self.bookmark_id,
            "field": self.field,
            "proposed_values": [copy.deepcopy(value) for value in self.proposed_values],
            "rule_ids": list(self.rule_ids),
            "rule_names": list(self.rule_names),
            "message": self.message,
        }


@dataclass
class OrganizationPreview:
    """Immutable-in-practice plan data used to guard an apply operation."""

    evaluated_count: int = 0
    matched_bookmark_count: int = 0
    affected_bookmark_count: int = 0
    changes: List[OrganizationRuleChange] = field(default_factory=list)
    conflicts: List[OrganizationRuleConflict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    fingerprint: str = ""
    scope_ids: Tuple[int, ...] = ()
    truncated: bool = False
    before_snapshots: Dict[int, Bookmark] = field(default_factory=dict, repr=False)
    after_snapshots: Dict[int, Bookmark] = field(default_factory=dict, repr=False)

    @property
    def affected_count(self) -> int:
        return self.affected_bookmark_count

    @property
    def conflict_count(self) -> int:
        return len(self.conflicts)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def change_count(self) -> int:
        return len(self.changes)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evaluated_count": self.evaluated_count,
            "matched_bookmark_count": self.matched_bookmark_count,
            "affected_bookmark_count": self.affected_bookmark_count,
            "change_count": len(self.changes),
            "conflict_count": len(self.conflicts),
            "error_count": len(self.errors),
            "changes": [change.to_dict() for change in self.changes[:MAX_CHANGES]],
            "conflicts": [conflict.to_dict() for conflict in self.conflicts[:MAX_CONFLICTS]],
            "errors": list(self.errors[:MAX_ERRORS]),
            "fingerprint": self.fingerprint,
            "scope_ids": list(self.scope_ids),
            "truncated": self.truncated,
        }


@dataclass
class OrganizationRunReport:
    """Persistable summary of the most recent preview/apply/undo operation."""

    status: str = "never_run"
    started_at: str = ""
    finished_at: str = ""
    evaluated_count: int = 0
    matched_bookmark_count: int = 0
    affected_bookmark_count: int = 0
    change_count: int = 0
    conflict_count: int = 0
    error_count: int = 0
    conflicts: List[OrganizationRuleConflict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    undo_available: bool = False

    @property
    def affected_count(self) -> int:
        return self.affected_bookmark_count

    @property
    def conflict_messages(self) -> List[str]:
        return [conflict.message for conflict in self.conflicts]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "evaluated_count": self.evaluated_count,
            "matched_bookmark_count": self.matched_bookmark_count,
            "affected_bookmark_count": self.affected_bookmark_count,
            "change_count": self.change_count,
            "conflict_count": self.conflict_count,
            "error_count": self.error_count,
            "conflicts": [conflict.to_dict() for conflict in self.conflicts[:MAX_CONFLICTS]],
            "errors": list(self.errors[:MAX_ERRORS]),
            "undo_available": self.undo_available,
        }

    @classmethod
    def from_dict(cls, data: Any) -> Optional["OrganizationRunReport"]:
        if not isinstance(data, Mapping):
            return None
        conflicts: List[OrganizationRuleConflict] = []
        for raw in data.get("conflicts", [])[:MAX_CONFLICTS] if isinstance(data.get("conflicts", []), list) else []:
            try:
                conflicts.append(
                    OrganizationRuleConflict(
                        bookmark_id=int(raw.get("bookmark_id", 0)),
                        field=_text(raw.get("field"), limit=80),
                        proposed_values=tuple(raw.get("proposed_values", [])),
                        rule_ids=tuple(_text(value, limit=MAX_ID_LENGTH) for value in raw.get("rule_ids", [])),
                        rule_names=tuple(_text(value, limit=MAX_NAME_LENGTH) for value in raw.get("rule_names", [])),
                        message=_text(raw.get("message"), limit=MAX_VALUE_LENGTH),
                    )
                )
            except (TypeError, ValueError, AttributeError):
                continue
        errors = data.get("errors", [])
        if not isinstance(errors, list):
            errors = []
        return cls(
            status=_text(data.get("status"), limit=40) or "unknown",
            started_at=_text(data.get("started_at"), limit=64),
            finished_at=_text(data.get("finished_at"), limit=64),
            evaluated_count=max(0, int(data.get("evaluated_count", 0) or 0)),
            matched_bookmark_count=max(0, int(data.get("matched_bookmark_count", 0) or 0)),
            affected_bookmark_count=max(0, int(data.get("affected_bookmark_count", 0) or 0)),
            change_count=max(0, int(data.get("change_count", 0) or 0)),
            conflict_count=max(0, int(data.get("conflict_count", len(conflicts)) or 0)),
            error_count=max(0, int(data.get("error_count", len(errors)) or 0)),
            conflicts=conflicts,
            errors=[_text(value) for value in errors[:MAX_ERRORS]],
            undo_available=bool(data.get("undo_available", False)),
        )


class OrganizationRulesService:
    """Manage validated organization rules for one bookmark manager."""

    RULES_FILE = DATA_DIR / "organization_rules.json"
    LEGACY_RULES_FILE = DATA_DIR / "smart_tag_rules.json"

    def __init__(self, bookmark_manager):
        self.bookmark_manager = bookmark_manager
        self.rules: List[OrganizationRule] = []
        self.last_run: Optional[OrganizationRunReport] = None
        self.load_errors: List[str] = []
        self._undo_snapshot: Optional[Dict[int, Tuple[Bookmark, Bookmark]]] = None
        self._load()

    @property
    def last_run_report(self) -> Optional[OrganizationRunReport]:
        return self.last_run

    def _load(self) -> None:
        path = Path(self.RULES_FILE)
        if path.exists():
            try:
                if path.stat().st_size > MAX_IMPORT_BYTES:
                    raise ValueError("Organization rules file exceeds the size limit")
                with path.open("r", encoding="utf-8") as handle:
                    document = json.load(handle)
                self.rules = self._validated_document(document)
                self.last_run = OrganizationRunReport.from_dict(document.get("last_run"))
            except Exception as exc:
                self.rules = []
                self.last_run = None
                self.load_errors = [f"Rules file ignored: {exc}"]
                log.warning(self.load_errors[0])
            return

        migrated = self._migrate_legacy_rules()
        self.rules = migrated
        if migrated:
            try:
                self._save()
            except OSError as exc:
                self.load_errors.append(f"Migrated rules could not be saved: {exc}")
                log.warning(self.load_errors[-1])

    @classmethod
    def _validated_document(cls, document: Any) -> List[OrganizationRule]:
        if not isinstance(document, Mapping):
            raise ValueError("Organization rules document must be an object")
        if document.get("schema") != ORGANIZATION_RULES_SCHEMA:
            raise ValueError("Unsupported organization rules schema")
        if document.get("schema_version") != ORGANIZATION_RULES_VERSION:
            raise ValueError("Unsupported organization rules version")
        raw_rules = document.get("rules")
        if not isinstance(raw_rules, list):
            raise ValueError("Organization rules must be a list")
        if len(raw_rules) > MAX_RULES:
            raise ValueError(f"Organization rules are limited to {MAX_RULES} rules")
        rules: List[OrganizationRule] = []
        seen_ids = set()
        for raw_rule in raw_rules:
            rule = OrganizationRule.from_dict(raw_rule)
            if rule.rule_id in seen_ids:
                raise ValueError(f"Duplicate organization rule ID: {rule.rule_id}")
            seen_ids.add(rule.rule_id)
            rules.append(rule)
        return rules

    def _migrate_legacy_rules(self) -> List[OrganizationRule]:
        legacy_path = Path(getattr(self, "LEGACY_RULES_FILE", self.LEGACY_RULES_FILE))
        default_legacy_path = Path(DATA_DIR) / "smart_tag_rules.json"
        if legacy_path == default_legacy_path:
            try:
                from bookmark_organizer_pro.services.organization import SmartTagManager

                legacy_path = Path(getattr(SmartTagManager, "RULES_FILE", legacy_path))
            except Exception:
                pass
        try:
            if not legacy_path.exists() or legacy_path.stat().st_size > MAX_IMPORT_BYTES:
                return []
            with legacy_path.open("r", encoding="utf-8") as handle:
                raw_rules = json.load(handle)
        except Exception as exc:
            self.load_errors.append(f"Legacy smart-tag rules could not be read: {exc}")
            return []
        if not isinstance(raw_rules, list):
            self.load_errors.append("Legacy smart-tag rules were not a list")
            return []

        migrated: List[OrganizationRule] = []
        for raw_rule in raw_rules[:MAX_RULES]:
            if not isinstance(raw_rule, Mapping):
                continue
            try:
                name = _text(raw_rule.get("name"), limit=MAX_NAME_LENGTH)
                tag = _text(raw_rule.get("tag"), limit=MAX_TAG_LENGTH)
                conditions = raw_rule.get("conditions", [])
                if not name or not tag or not isinstance(conditions, list):
                    continue
                migrated.append(
                    OrganizationRule(
                        name=name,
                        conditions=tuple(conditions),
                        actions=({"action": "add_tag", "value": tag},),
                        enabled=raw_rule.get("enabled", True),
                        rule_id=_canonical_id(name),
                        created_at=raw_rule.get("created_at", ""),
                    )
                )
            except (TypeError, ValueError) as exc:
                self.load_errors.append(f"Legacy rule skipped: {exc}")
        return migrated

    def _document(self) -> Dict[str, Any]:
        return {
            "schema": ORGANIZATION_RULES_SCHEMA,
            "schema_version": ORGANIZATION_RULES_VERSION,
            "rules": [rule.to_dict() for rule in self.rules],
            "last_run": self.last_run.to_dict() if self.last_run else None,
        }

    def _save(self) -> None:
        atomic_json_write(Path(self.RULES_FILE), self._document())

    def list_rules(self, *, include_disabled: bool = True) -> List[OrganizationRule]:
        rules = self.rules if include_disabled else [rule for rule in self.rules if rule.enabled]
        return [copy.deepcopy(rule) for rule in rules]

    def add_rule(self, rule: OrganizationRule | Mapping[str, Any]) -> OrganizationRule:
        normalized = rule if isinstance(rule, OrganizationRule) else OrganizationRule.from_dict(rule)
        replaced = False
        for index, existing in enumerate(self.rules):
            if existing.rule_id == normalized.rule_id or existing.name.casefold() == normalized.name.casefold():
                self.rules[index] = normalized
                replaced = True
                break
        if not replaced:
            if len(self.rules) >= MAX_RULES:
                raise ValueError(f"Organization rules are limited to {MAX_RULES} rules")
            self.rules.append(normalized)
        self._save()
        return copy.deepcopy(normalized)

    upsert_rule = add_rule

    def remove_rule(self, rule_id_or_name: str) -> bool:
        needle = _text(rule_id_or_name, limit=MAX_ID_LENGTH)
        before = len(self.rules)
        self.rules = [
            rule for rule in self.rules
            if rule.rule_id != needle and rule.name.casefold() != needle.casefold()
        ]
        if len(self.rules) == before:
            return False
        self._save()
        return True

    def set_enabled(self, rule_id_or_name: str, enabled: bool) -> Optional[OrganizationRule]:
        needle = _text(rule_id_or_name, limit=MAX_ID_LENGTH)
        enabled_value = _strict_bool(enabled, label="Rule enabled")
        for index, rule in enumerate(self.rules):
            if rule.rule_id == needle or rule.name.casefold() == needle.casefold():
                updated = OrganizationRule(
                    name=rule.name,
                    conditions=rule.conditions,
                    actions=rule.actions,
                    enabled=enabled_value,
                    rule_id=rule.rule_id,
                    created_at=rule.created_at,
                    updated_at=_now(),
                )
                self.rules[index] = updated
                self._save()
                return copy.deepcopy(updated)
        return None

    def enable_rule(self, rule_id_or_name: str) -> Optional[OrganizationRule]:
        return self.set_enabled(rule_id_or_name, True)

    def disable_rule(self, rule_id_or_name: str) -> Optional[OrganizationRule]:
        return self.set_enabled(rule_id_or_name, False)

    def _bookmarks_for_scope(self, bookmarks: Optional[Iterable[Bookmark]]) -> Tuple[List[Bookmark], bool]:
        source = self.bookmark_manager.get_all_bookmarks() if bookmarks is None else list(bookmarks)
        valid: List[Bookmark] = []
        seen_ids = set()
        errors = False
        for bookmark in source:
            if not isinstance(bookmark, Bookmark):
                errors = True
                continue
            try:
                bookmark_id = int(bookmark.id)
            except (TypeError, ValueError):
                errors = True
                continue
            if bookmark_id in seen_ids:
                errors = True
                continue
            seen_ids.add(bookmark_id)
            valid.append(bookmark)
        valid.sort(key=lambda item: (int(item.id), str(item.title or item.url).casefold(), str(item.url).casefold()))
        truncated = len(valid) > MAX_BOOKMARKS
        return valid[:MAX_BOOKMARKS], truncated or errors

    def _fingerprint(self, bookmarks: Sequence[Bookmark]) -> str:
        return _json_fingerprint(
            {
                "rules": [rule.to_dict() for rule in self.rules],
                "bookmarks": [bookmark.to_dict() for bookmark in bookmarks],
            }
        )

    @staticmethod
    def _condition_value(bookmark: Bookmark, field_name: str) -> Any:
        if field_name == "domain":
            return bookmark.domain
        if field_name == "tag":
            return list(bookmark.tags)
        if field_name == "pinned":
            return bool(bookmark.is_pinned)
        if field_name == "archived":
            return bool(bookmark.is_archived)
        if field_name == "read_later":
            return bool(bookmark.read_later)
        return str(getattr(bookmark, field_name, "") or "")

    @staticmethod
    def _matches_condition(bookmark: Bookmark, condition: Mapping[str, str]) -> bool:
        field_name = condition["field"]
        operator = condition["operator"]
        raw_value = condition.get("value", "")
        actual = OrganizationRulesService._condition_value(bookmark, field_name)
        if operator == "is_true":
            return bool(actual) is True
        if operator == "is_false":
            return bool(actual) is False
        if field_name in BOOLEAN_FIELDS:
            expected = _strict_bool(raw_value, label=f"Condition value for {field_name}")
            if operator == "equals":
                return actual is expected
            if operator == "not_equals":
                return actual is not expected
            return False

        expected_text = str(raw_value).casefold()
        if field_name == "tag":
            values = [str(value or "") for value in actual]
            if operator == "contains":
                return any(expected_text in value.casefold() for value in values)
            if operator == "starts_with":
                return any(value.casefold().startswith(expected_text) for value in values)
            if operator == "ends_with":
                return any(value.casefold().endswith(expected_text) for value in values)
            if operator == "equals":
                return any(value.casefold() == expected_text for value in values)
            if operator == "not_equals":
                return all(value.casefold() != expected_text for value in values)
            if operator == "regex":
                return any(
                    bool(regex.search(raw_value, value, regex.IGNORECASE, timeout=REGEX_TIMEOUT_SECONDS))
                    for value in values
                )
            return False

        actual_text = str(actual or "")
        if operator == "contains":
            return expected_text in actual_text.casefold()
        if operator == "starts_with":
            return actual_text.casefold().startswith(expected_text)
        if operator == "ends_with":
            return actual_text.casefold().endswith(expected_text)
        if operator == "equals":
            return actual_text.casefold() == expected_text
        if operator == "not_equals":
            return actual_text.casefold() != expected_text
        if operator == "regex":
            return bool(regex.search(raw_value, actual_text, regex.IGNORECASE, timeout=REGEX_TIMEOUT_SECONDS))
        return False

    def _rule_matches(self, bookmark: Bookmark, rule: OrganizationRule) -> Tuple[bool, Optional[str]]:
        try:
            return all(self._matches_condition(bookmark, condition) for condition in rule.conditions), None
        except (regex.error, TimeoutError) as exc:
            return False, f"Rule '{rule.name}' was skipped for bookmark {bookmark.id}: regex evaluation failed ({exc})."
        except Exception as exc:
            return False, f"Rule '{rule.name}' was skipped for bookmark {bookmark.id}: {exc}."

    @staticmethod
    def _action_proposals(matches: Sequence[Tuple[OrganizationRule, Mapping[str, Any]]], action_names: set[str]):
        return [
            (rule, action)
            for rule, action in matches
            if action.get("action") in action_names
        ]

    @staticmethod
    def _conflict(
        bookmark_id: int,
        field_name: str,
        proposals: Sequence[Tuple[OrganizationRule, Mapping[str, Any]]],
        values: Sequence[Any],
        message: str,
    ) -> OrganizationRuleConflict:
        return OrganizationRuleConflict(
            bookmark_id=bookmark_id,
            field=field_name,
            proposed_values=tuple(copy.deepcopy(value) for value in values),
            rule_ids=tuple(rule.rule_id for rule, _action in proposals),
            rule_names=tuple(rule.name for rule, _action in proposals),
            message=message,
        )

    def _plan_bookmark(
        self,
        bookmark: Bookmark,
        matches: Sequence[Tuple[OrganizationRule, Mapping[str, Any]]],
    ) -> Tuple[Bookmark, List[OrganizationRuleChange], List[OrganizationRuleConflict]]:
        planned = copy.deepcopy(bookmark)
        changes: List[OrganizationRuleChange] = []
        conflicts: List[OrganizationRuleConflict] = []

        field_specs = (
            ("category", "set_category", "category"),
            ("read_later", "set_read_later", "read_later"),
            ("pinned", "set_pinned", "is_pinned"),
            ("archived", "set_archived", "is_archived"),
        )
        for field_name, action_name, attribute in field_specs:
            proposals = self._action_proposals(matches, {action_name})
            if not proposals:
                continue
            unique_values: List[Any] = []
            for _rule, action in proposals:
                value = action["value"]
                if value not in unique_values:
                    unique_values.append(value)
            if len(unique_values) > 1:
                conflicts.append(
                    self._conflict(
                        int(bookmark.id),
                        field_name,
                        proposals,
                        unique_values,
                        f"Conflicting {field_name} values were skipped.",
                    )
                )
                continue
            setattr(planned, attribute, copy.deepcopy(unique_values[0]))
            sources = tuple(dict.fromkeys(rule.rule_id for rule, _action in proposals))
            names = tuple(dict.fromkeys(rule.name for rule, _action in proposals))
            if getattr(bookmark, attribute) != getattr(planned, attribute):
                changes.append(
                    OrganizationRuleChange(
                        bookmark_id=int(bookmark.id),
                        field=field_name,
                        before=copy.deepcopy(getattr(bookmark, attribute)),
                        after=copy.deepcopy(getattr(planned, attribute)),
                        rule_ids=sources,
                        rule_names=names,
                    )
                )

        tag_proposals = self._action_proposals(matches, {"add_tag", "remove_tag"})
        by_tag: Dict[str, List[Tuple[OrganizationRule, Mapping[str, Any]]]] = {}
        for rule, action in tag_proposals:
            tag_key = str(action["value"]).casefold()
            by_tag.setdefault(tag_key, []).append((rule, action))
        next_tags = list(bookmark.tags)
        for tag_key, proposals in by_tag.items():
            add = [item for item in proposals if item[1]["action"] == "add_tag"]
            remove = [item for item in proposals if item[1]["action"] == "remove_tag"]
            if add and remove:
                conflicts.append(
                    self._conflict(
                        int(bookmark.id),
                        f"tag:{tag_key}",
                        proposals,
                        ["add", "remove"],
                        f"Conflicting add/remove actions for tag '{tag_key}' were skipped.",
                    )
                )
                continue
            if add:
                requested = str(add[0][1]["value"])
                if not any(str(existing).casefold() == tag_key for existing in next_tags):
                    next_tags.append(requested)
            elif remove:
                next_tags = [existing for existing in next_tags if str(existing).casefold() != tag_key]
        if next_tags != bookmark.tags:
            tag_sources = tuple(dict.fromkeys(rule.rule_id for rule, _action in tag_proposals))
            tag_names = tuple(dict.fromkeys(rule.name for rule, _action in tag_proposals))
            planned.tags = next_tags
            changes.append(
                OrganizationRuleChange(
                    bookmark_id=int(bookmark.id),
                    field="tags",
                    before=list(bookmark.tags),
                    after=list(next_tags),
                    rule_ids=tag_sources,
                    rule_names=tag_names,
                )
            )

        return planned, changes, conflicts

    def preview(self, bookmarks: Optional[Iterable[Bookmark]] = None) -> OrganizationPreview:
        selected, truncated_or_invalid = self._bookmarks_for_scope(bookmarks)
        scope_ids = tuple(int(bookmark.id) for bookmark in selected)
        errors: List[str] = []
        if truncated_or_invalid:
            errors.append(f"Evaluation was bounded to {MAX_BOOKMARKS} valid bookmarks.")
        changes: List[OrganizationRuleChange] = []
        conflicts: List[OrganizationRuleConflict] = []
        before_snapshots: Dict[int, Bookmark] = {}
        after_snapshots: Dict[int, Bookmark] = {}
        matched_count = 0
        error_seen = set()
        enabled_rules = [rule for rule in self.rules if rule.enabled]

        for bookmark in selected:
            matches: List[Tuple[OrganizationRule, Mapping[str, Any]]] = []
            for rule in enabled_rules:
                matched, error = self._rule_matches(bookmark, rule)
                if error and error not in error_seen and len(errors) < MAX_ERRORS:
                    errors.append(error)
                    error_seen.add(error)
                if matched:
                    matches.extend((rule, action) for action in rule.actions)
            if matches:
                matched_count += 1
            if not matches:
                continue
            planned, bookmark_changes, bookmark_conflicts = self._plan_bookmark(bookmark, matches)
            if bookmark_conflicts:
                conflicts.extend(bookmark_conflicts[: max(0, MAX_CONFLICTS - len(conflicts))])
            if bookmark_changes:
                bookmark_id = int(bookmark.id)
                before_snapshots[bookmark_id] = copy.deepcopy(bookmark)
                after_snapshots[bookmark_id] = planned
                remaining = max(0, MAX_CHANGES - len(changes))
                if remaining:
                    changes.extend(bookmark_changes[:remaining])
                if len(changes) >= MAX_CHANGES:
                    errors.append(f"Preview changes were bounded to {MAX_CHANGES} field transitions.")
                    break

        fingerprint = self._fingerprint(selected)
        return OrganizationPreview(
            evaluated_count=len(selected),
            matched_bookmark_count=matched_count,
            affected_bookmark_count=len(before_snapshots),
            changes=changes,
            conflicts=conflicts,
            errors=errors[:MAX_ERRORS],
            fingerprint=fingerprint,
            scope_ids=scope_ids,
            truncated=truncated_or_invalid,
            before_snapshots=before_snapshots,
            after_snapshots=after_snapshots,
        )

    def _report_from_preview(
        self,
        preview: OrganizationPreview,
        *,
        status: str,
        started_at: str,
        finished_at: Optional[str] = None,
        errors: Optional[List[str]] = None,
        undo_available: bool = False,
    ) -> OrganizationRunReport:
        merged_errors = list(preview.errors)
        for error in errors or []:
            if error not in merged_errors and len(merged_errors) < MAX_ERRORS:
                merged_errors.append(error)
        return OrganizationRunReport(
            status=status,
            started_at=started_at,
            finished_at=finished_at or _now(),
            evaluated_count=preview.evaluated_count,
            matched_bookmark_count=preview.matched_bookmark_count,
            affected_bookmark_count=preview.affected_bookmark_count,
            change_count=len(preview.changes),
            conflict_count=len(preview.conflicts),
            error_count=len(merged_errors),
            conflicts=list(preview.conflicts[:MAX_CONFLICTS]),
            errors=merged_errors[:MAX_ERRORS],
            undo_available=undo_available,
        )

    def _persist_last_run(self, report: OrganizationRunReport) -> None:
        self.last_run = report
        try:
            self._save()
        except OSError as exc:
            log.warning("Could not persist organization rule run report: %s", exc)

    def _current_scope(self, scope_ids: Sequence[int]) -> Optional[List[Bookmark]]:
        by_id = {int(bookmark.id): bookmark for bookmark in self.bookmark_manager.get_all_bookmarks()}
        current = []
        for bookmark_id in scope_ids:
            bookmark = by_id.get(int(bookmark_id))
            if bookmark is None:
                return None
            current.append(bookmark)
        current.sort(key=lambda item: (int(item.id), str(item.title or item.url).casefold(), str(item.url).casefold()))
        return current

    def apply(self, preview: Optional[OrganizationPreview] = None) -> OrganizationRunReport:
        started_at = _now()
        preview = preview or self.preview()
        current_scope = self._current_scope(preview.scope_ids)
        if current_scope is None or self._fingerprint(current_scope) != preview.fingerprint:
            report = self._report_from_preview(
                preview,
                status="stale",
                started_at=started_at,
                errors=["Preview is stale because bookmarks or rules changed; run preview again."],
            )
            self._persist_last_run(report)
            return report
        if not preview.after_snapshots:
            report = self._report_from_preview(preview, status="no_changes", started_at=started_at)
            self._persist_last_run(report)
            self._undo_snapshot = None
            return report

        before = {bookmark_id: copy.deepcopy(snapshot) for bookmark_id, snapshot in preview.before_snapshots.items()}
        after = {bookmark_id: copy.deepcopy(snapshot) for bookmark_id, snapshot in preview.after_snapshots.items()}
        timestamp = _now()
        for snapshot in after.values():
            snapshot.modified_at = timestamp
        try:
            with self.bookmark_manager.batch():
                for bookmark_id, snapshot in after.items():
                    if bookmark_id not in self.bookmark_manager.bookmarks:
                        raise ValueError(f"Bookmark {bookmark_id} disappeared during apply")
                    self.bookmark_manager.bookmarks[bookmark_id] = copy.deepcopy(snapshot)
                self.bookmark_manager.save_bookmarks()
        except Exception as exc:
            report = self._report_from_preview(
                preview,
                status="failed",
                started_at=started_at,
                errors=[f"Organization rule batch failed: {exc}"],
            )
            self._persist_last_run(report)
            self._undo_snapshot = None
            return report

        self._undo_snapshot = {bookmark_id: (before[bookmark_id], after[bookmark_id]) for bookmark_id in before}
        report = self._report_from_preview(
            preview,
            status="applied",
            started_at=started_at,
            undo_available=True,
        )
        self._persist_last_run(report)
        return report

    def undo_last(self) -> OrganizationRunReport:
        started_at = _now()
        if not self._undo_snapshot:
            report = OrganizationRunReport(
                status="no_undo",
                started_at=started_at,
                finished_at=_now(),
                errors=["There is no organization rule run available to undo."],
                error_count=1,
            )
            self._persist_last_run(report)
            return report

        current = {int(bookmark.id): bookmark for bookmark in self.bookmark_manager.get_all_bookmarks()}
        errors: List[str] = []
        for bookmark_id, (_before, after) in self._undo_snapshot.items():
            present = current.get(bookmark_id)
            if present is None:
                errors.append(f"Bookmark {bookmark_id} is no longer available; undo was not applied.")
                continue
            if _json_fingerprint(present.to_dict()) != _json_fingerprint(after.to_dict()):
                errors.append(f"Bookmark {bookmark_id} changed after the rule run; undo was not applied.")
        if errors:
            report = OrganizationRunReport(
                status="undo_conflict",
                started_at=started_at,
                finished_at=_now(),
                affected_bookmark_count=len(self._undo_snapshot),
                error_count=min(len(errors), MAX_ERRORS),
                errors=errors[:MAX_ERRORS],
                undo_available=True,
            )
            self._persist_last_run(report)
            return report

        try:
            with self.bookmark_manager.batch():
                for bookmark_id, (before, _after) in self._undo_snapshot.items():
                    self.bookmark_manager.bookmarks[bookmark_id] = copy.deepcopy(before)
                self.bookmark_manager.save_bookmarks()
        except Exception as exc:
            report = OrganizationRunReport(
                status="failed",
                started_at=started_at,
                finished_at=_now(),
                affected_bookmark_count=len(self._undo_snapshot),
                error_count=1,
                errors=[f"Organization undo failed: {exc}"],
                undo_available=True,
            )
            self._persist_last_run(report)
            return report

        count = len(self._undo_snapshot)
        self._undo_snapshot = None
        report = OrganizationRunReport(
            status="undone",
            started_at=started_at,
            finished_at=_now(),
            affected_bookmark_count=count,
            change_count=count,
            undo_available=False,
        )
        self._persist_last_run(report)
        return report

    @classmethod
    def _read_document(cls, path: Path) -> Dict[str, Any]:
        path = Path(path)
        if path.stat().st_size > MAX_IMPORT_BYTES:
            raise ValueError("Organization rules import exceeds the size limit")
        with path.open("r", encoding="utf-8") as handle:
            document = json.load(handle)
        cls._validated_document(document)
        return document

    def export_rules(self, path: str | Path) -> Path:
        target = Path(path)
        atomic_json_write(
            target,
            {
                "schema": ORGANIZATION_RULES_SCHEMA,
                "schema_version": ORGANIZATION_RULES_VERSION,
                "rules": [rule.to_dict() for rule in self.rules],
            },
        )
        return target

    export = export_rules

    def import_rules(self, path: str | Path, *, replace: bool = False) -> int:
        document = self._read_document(Path(path))
        imported = [OrganizationRule.from_dict(raw_rule) for raw_rule in document["rules"]]
        if replace:
            self.rules = imported
        else:
            merged = list(self.rules)
            for incoming in imported:
                replacement_index = next(
                    (
                        index for index, existing in enumerate(merged)
                        if existing.rule_id == incoming.rule_id
                        or existing.name.casefold() == incoming.name.casefold()
                    ),
                    None,
                )
                if replacement_index is None:
                    if len(merged) >= MAX_RULES:
                        raise ValueError(f"Organization rules are limited to {MAX_RULES} rules")
                    merged.append(incoming)
                else:
                    merged[replacement_index] = incoming
            self.rules = merged
        self._save()
        return len(imported)

    import_from = import_rules


OrganizationRules = OrganizationRulesService


__all__ = [
    "ALLOWED_ACTIONS",
    "ALLOWED_FIELDS",
    "ALLOWED_OPERATORS",
    "MAX_ACTIONS",
    "MAX_BOOKMARKS",
    "MAX_CONDITIONS",
    "MAX_RULES",
    "OrganizationPreview",
    "OrganizationRule",
    "OrganizationRuleChange",
    "OrganizationRuleConflict",
    "OrganizationRules",
    "OrganizationRulesService",
    "OrganizationRunReport",
    "ORGANIZATION_RULES_SCHEMA",
    "ORGANIZATION_RULES_VERSION",
    "RULES_SCHEMA",
    "RULES_VERSION",
]
