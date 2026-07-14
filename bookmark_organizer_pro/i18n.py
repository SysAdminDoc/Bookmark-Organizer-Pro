"""Internationalization scaffolding via gettext.

Usage in any module::

    from bookmark_organizer_pro.i18n import _

    label = _("All Links")

At startup the app calls ``setup_locale()`` once. If no translation files
exist the passthrough identity function is used — zero overhead, zero risk.

Translation files live under ``locale/<lang>/LC_MESSAGES/bop.mo``.
Generate the template with::

    python -m bookmark_organizer_pro.i18n

That scans all ``.py`` files for ``_("...")`` calls and writes
``locale/bop.pot``.
"""

from __future__ import annotations

import gettext
import json
import locale
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from string import Formatter
from typing import Sequence

_LOCALE_DIR = Path(__file__).resolve().parent.parent / "locale"
_DOMAIN = "bop"
POT_PATH = _LOCALE_DIR / f"{_DOMAIN}.pot"
EXTENSION_DIR = Path(__file__).resolve().parent.parent / "browser-extension"

_translation: gettext.GNUTranslations | gettext.NullTranslations = gettext.NullTranslations()
_active_language = "en"
_RTL_LANGUAGES = {"ar", "dv", "fa", "he", "ku", "ps", "ur", "qps-plocm"}
_PSEUDO_ACCENTS = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
    "ÅƁÇÐÉƑĜĤÎĴҠĿḾŃÖƤQŔŞŢÛṼŴẊÝŽåƀçðéƒĝĥîĵҡŀḿńöƥqŕşţûṽŵẋýž",
)
_FORMAT_TOKEN = re.compile(r"(\{[^{}]+\}|%\([^)]+\)[#0 +\-]?[0-9.]?[a-zA-Z]|%[sdif])")
_UI_LITERAL_KEYWORDS = {"label", "message", "placeholder", "prompt", "text", "title", "tooltip"}
_MESSAGE_METHODS = {"askokcancel", "askyesno", "showerror", "showinfo", "showwarning"}
_TRANSLATION_CALLS = {"_", "N_", "format_message", "format_plural", "ngettext"}
_EXTENSION_PLACEHOLDER = re.compile(r"\$([A-Za-z][A-Za-z0-9_]*)\$")
_EXTENSION_UI_ASSIGNMENT = re.compile(
    r"(?:textContent|innerText|placeholder|\.title)\s*=\s*([\"'`])(.*?)\1\s*;"
)
_EXTENSION_MESSAGE_CALL = re.compile(
    r"extensionMessage\(\s*([\"'])([A-Za-z0-9_@]+)\1\s*,\s*\[([^\]]*)\]"
)


def _(message: str) -> str:
    return _translation.gettext(message)


def N_(message: str) -> str:
    """Mark a deferred string for extraction without translating at import time."""
    return message


def ngettext(singular: str, plural: str, n: int) -> str:
    return _translation.ngettext(singular, plural, n)


def format_message(message: str, /, **values) -> str:
    """Translate a named-placeholder template before formatting it."""
    return _(message).format(**values)


def format_plural(singular: str, plural: str, n: int, /, **values) -> str:
    """Select a translated plural form before applying named placeholders."""
    return ngettext(singular, plural, n).format(**values)


def pseudo_localize(message: str, *, rtl: bool = False) -> str:
    """Expand a message while preserving interpolation tokens for layout QA."""
    parts = _FORMAT_TOKEN.split(message)
    transformed = "".join(
        part if _FORMAT_TOKEN.fullmatch(part) else part.translate(_PSEUDO_ACCENTS)
        for part in parts
    )
    padding = "~" * max(2, len(message) // 3)
    rendered = f"⟦{transformed} {padding}⟧"
    return f"\u202b{rendered}\u202c" if rtl else rendered


class PseudoTranslations(gettext.NullTranslations):
    def __init__(self, *, rtl: bool = False):
        super().__init__()
        self.rtl = rtl

    def gettext(self, message: str) -> str:
        return pseudo_localize(message, rtl=self.rtl)

    def ngettext(self, singular: str, plural: str, n: int) -> str:
        return self.gettext(singular if n == 1 else plural)


def active_language() -> str:
    return _active_language


def is_rtl(lang: str | None = None) -> bool:
    code = (lang or _active_language).replace("_", "-").lower()
    return code in _RTL_LANGUAGES or code.split("-", 1)[0] in _RTL_LANGUAGES


def layout_side(side: str, lang: str | None = None) -> str:
    """Mirror Tk pack sides for RTL locales."""
    if not is_rtl(lang):
        return side
    return {"left": "right", "right": "left"}.get(str(side).lower(), side)


def layout_anchor(anchor: str, lang: str | None = None) -> str:
    """Mirror cardinal Tk anchors for RTL locales."""
    if not is_rtl(lang):
        return anchor
    return {"w": "e", "e": "w", "nw": "ne", "ne": "nw", "sw": "se", "se": "sw"}.get(
        str(anchor).lower(), anchor,
    )


def setup_locale(lang: str = ""):
    """Initialize translations for *lang* (or the system default).

    Call once at app startup. Safe to call multiple times — later calls
    replace the active translation.
    """
    global _active_language, _translation
    if not lang:
        lang = locale.getlocale()[0] or "en"

    normalized = lang.replace("_", "-").lower()
    _active_language = normalized
    if normalized in {"qps-ploc", "en-xa"}:
        _translation = PseudoTranslations()
        return
    if normalized in {"qps-plocm", "ar-xb"}:
        _translation = PseudoTranslations(rtl=True)
        return

    if _LOCALE_DIR.is_dir():
        try:
            _translation = gettext.translation(
                _DOMAIN, localedir=str(_LOCALE_DIR), languages=[lang],
                fallback=True,
            )
            return
        except Exception:
            pass

    _translation = gettext.NullTranslations()


def _escape_pot(message: str) -> str:
    return message.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _call_name(node) -> str:
    import ast

    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _ui_literal_expressions(call):
    """Yield high-confidence user-facing expressions from a UI call."""
    import ast

    for keyword in call.keywords:
        if keyword.arg in _UI_LITERAL_KEYWORDS:
            yield keyword.arg, keyword.value
    method = call.func.attr if isinstance(call.func, ast.Attribute) else ""
    if method == "title":
        for argument in call.args[:1]:
            yield "title", argument
    elif method in _MESSAGE_METHODS:
        for index, argument in enumerate(call.args[:2]):
            yield "title" if index == 0 else "message", argument


def _untranslated_expressions(expression):
    """Yield literal UI expressions not protected by a translation call."""
    import ast

    if isinstance(expression, ast.Call) and _call_name(expression.func) in _TRANSLATION_CALLS:
        return
    if isinstance(expression, (ast.Constant, ast.JoinedStr)):
        if not isinstance(expression, ast.Constant) or (
            isinstance(expression.value, str) and expression.value.strip()
        ):
            yield expression
        return
    if isinstance(expression, ast.IfExp):
        yield from _untranslated_expressions(expression.body)
        yield from _untranslated_expressions(expression.orelse)
    elif isinstance(expression, ast.BinOp) and isinstance(expression.op, ast.Add):
        yield from _untranslated_expressions(expression.left)
        yield from _untranslated_expressions(expression.right)


def desktop_literal_violations(src_root: Path | None = None) -> list[str]:
    """Return unwrapped high-confidence desktop UI literals."""
    import ast

    src_root = src_root or Path(__file__).resolve().parent
    violations: list[str] = []
    for py_file in sorted(src_root.rglob("*.py")):
        if py_file.resolve() == Path(__file__).resolve():
            continue
        rel = py_file.relative_to(src_root.parent).as_posix()
        if "/ui/" not in f"/{rel}" and "/app_mixins/" not in f"/{rel}":
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(rel))
        except SyntaxError as exc:
            violations.append(f"{rel}:{exc.lineno or 1}: cannot audit invalid Python")
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for context, expression in _ui_literal_expressions(node):
                for literal in _untranslated_expressions(expression):
                    violations.append(
                        f"{rel}:{literal.lineno}: {context} literal must use _(), "
                        "ngettext(), N_(), or format_message()"
                    )
    return violations


def _format_fields(message: str) -> set[str]:
    fields: set[str] = set()
    try:
        parsed = Formatter().parse(message)
        for _literal, field_name, _format_spec, _conversion in parsed:
            if field_name:
                fields.add(field_name.split(".", 1)[0].split("[", 1)[0])
    except ValueError:
        return {"<invalid>"}
    fields.update(token for token in _FORMAT_TOKEN.findall(message) if token.startswith("%"))
    return fields


def desktop_placeholder_violations(src_root: Path | None = None) -> list[str]:
    """Validate named formatting and plural placeholders in desktop source."""
    import ast

    src_root = src_root or Path(__file__).resolve().parent
    violations: list[str] = []
    for py_file in sorted(src_root.rglob("*.py")):
        if py_file.resolve() == Path(__file__).resolve():
            continue
        rel = py_file.relative_to(src_root.parent).as_posix()
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(rel))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _call_name(node.func)
            if name == "format_message" and node.args:
                template = node.args[0]
                if not isinstance(template, ast.Constant) or not isinstance(template.value, str):
                    violations.append(f"{rel}:{node.lineno}: format_message template must be literal")
                    continue
                expected = _format_fields(template.value)
                actual = {keyword.arg for keyword in node.keywords if keyword.arg}
                if expected != actual:
                    violations.append(
                        f"{rel}:{node.lineno}: format_message placeholders "
                        f"{sorted(expected)} do not match arguments {sorted(actual)}"
                    )
            elif (
                isinstance(node.func, ast.Name)
                and name in {"format_plural", "ngettext"}
                and len(node.args) >= 2
            ):
                singular, plural = node.args[:2]
                if not all(
                    isinstance(value, ast.Constant) and isinstance(value.value, str)
                    for value in (singular, plural)
                ):
                    violations.append(f"{rel}:{node.lineno}: ngettext forms must be literal")
                    continue
                singular_fields = _format_fields(singular.value)
                plural_fields = _format_fields(plural.value)
                if singular_fields != plural_fields:
                    violations.append(
                        f"{rel}:{node.lineno}: ngettext placeholders differ between forms"
                    )
                elif name == "format_plural":
                    actual = {keyword.arg for keyword in node.keywords if keyword.arg}
                    if singular_fields != actual:
                        violations.append(
                            f"{rel}:{node.lineno}: format_plural placeholders "
                            f"{sorted(singular_fields)} do not match arguments {sorted(actual)}"
                        )
    return violations


def collect_translatable_strings(src_root: Path | None = None) -> dict[str, list[tuple[str, int]]]:
    """Scan literal gettext, deferred, plural, and formatted-message calls."""
    import ast

    src_root = src_root or Path(__file__).resolve().parent
    strings: dict[str, list[tuple[str, int]]] = {}

    for py_file in sorted(src_root.rglob("*.py")):
        rel = py_file.relative_to(src_root.parent).as_posix()
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(rel))
        except SyntaxError:
            continue
        def add(value, line_number: int) -> None:
            if isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value.strip():
                strings.setdefault(value.value, []).append((rel, line_number))

        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"_", "N_", "format_message"}
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                add(node.args[0], node.lineno)
    for locations in strings.values():
        locations.sort()

    return strings


def collect_plural_strings(
    src_root: Path | None = None,
) -> dict[tuple[str, str], list[tuple[str, int]]]:
    """Collect literal ngettext and format_plural pairs for POT plural entries."""
    import ast

    src_root = src_root or Path(__file__).resolve().parent
    plurals: dict[tuple[str, str], list[tuple[str, int]]] = {}
    for py_file in sorted(src_root.rglob("*.py")):
        rel = py_file.relative_to(src_root.parent).as_posix()
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(rel))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"format_plural", "ngettext"}
                and len(node.args) >= 2
                and all(
                    isinstance(argument, ast.Constant) and isinstance(argument.value, str)
                    for argument in node.args[:2]
                )
            ):
                continue
            pair = (node.args[0].value, node.args[1].value)
            plurals.setdefault(pair, []).append((rel, node.lineno))
    for locations in plurals.values():
        locations.sort()
    return plurals


def build_pot() -> str:
    """Build the gettext template contents from current source strings."""
    strings = collect_translatable_strings()
    plurals = collect_plural_strings()

    lines = [
        '# Bookmark Organizer Pro — Translation Template',
        '# This file is auto-generated. Do not edit manually.',
        '#',
        'msgid ""',
        'msgstr ""',
        '"Content-Type: text/plain; charset=UTF-8\\n"',
        '"Content-Transfer-Encoding: 8bit\\n"',
        '',
    ]
    for msg, locations in sorted(strings.items()):
        for rel, line_number in locations:
            lines.append(f"#: {rel}:{line_number}")
        lines.append(f'msgid "{_escape_pot(msg)}"')
        lines.append('msgstr ""')
        lines.append('')
    for (singular, plural), locations in sorted(plurals.items()):
        for rel, line_number in locations:
            lines.append(f"#: {rel}:{line_number}")
        if _format_fields(singular):
            lines.append("#, python-brace-format")
        lines.append(f'msgid "{_escape_pot(singular)}"')
        lines.append(f'msgid_plural "{_escape_pot(plural)}"')
        lines.append('msgstr[0] ""')
        lines.append('msgstr[1] ""')
        lines.append('')

    return "\n".join(lines)


def write_pot(pot_path: Path | None = None) -> int:
    """Write ``locale/bop.pot`` and return the number of translatable strings."""
    strings = collect_translatable_strings()
    plurals = collect_plural_strings()
    pot_path = pot_path or POT_PATH

    pot_path.parent.mkdir(parents=True, exist_ok=True)
    pot_path.write_text(build_pot(), encoding="utf-8")
    return len(strings) + len(plurals)


def pot_is_current(pot_path: Path | None = None) -> bool:
    """Return whether the committed template matches current source strings."""
    pot_path = pot_path or POT_PATH
    if not pot_path.exists():
        return False
    return pot_path.read_text(encoding="utf-8") == build_pot()


def extension_message_keys(extension_dir: Path | None = None) -> set[str]:
    """Collect manifest and HTML chrome.i18n keys used by extension documents."""
    extension_dir = extension_dir or EXTENSION_DIR
    keys: set[str] = set()
    manifest = (extension_dir / "manifest.json").read_text(encoding="utf-8")
    keys.update(re.findall(r"__MSG_([A-Za-z0-9_@]+)__", manifest))
    attribute = re.compile(
        r"data-i18n(?:-placeholder|-title|-aria-label)?=[\"']([A-Za-z0-9_@]+)[\"']"
    )
    for html_file in sorted(extension_dir.glob("*.html")):
        keys.update(attribute.findall(html_file.read_text(encoding="utf-8")))
    for js_file in sorted(extension_dir.glob("*.js")):
        source = js_file.read_text(encoding="utf-8")
        keys.update(re.findall(r"extensionMessage\(\s*[\"']([A-Za-z0-9_@]+)[\"']", source))
    return keys


def extension_missing_keys(extension_dir: Path | None = None, locale_name: str = "en") -> set[str]:
    extension_dir = extension_dir or EXTENSION_DIR
    catalog_path = extension_dir / "_locales" / locale_name / "messages.json"
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return extension_message_keys(extension_dir)
    available = {
        str(key) for key, value in catalog.items()
        if isinstance(value, dict) and isinstance(value.get("message"), str) and value["message"]
    }
    return extension_message_keys(extension_dir) - available


class _ExtensionHTMLAudit(HTMLParser):
    """Check that visible extension HTML copy routes through data-i18n."""

    _ATTRIBUTES = {
        "aria-label": "data-i18n-aria-label",
        "placeholder": "data-i18n-placeholder",
        "title": "data-i18n-title",
    }

    def __init__(self, rel: str):
        super().__init__()
        self.rel = rel
        self.stack: list[tuple[str, dict[str, str | None]]] = []
        self.violations: list[str] = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self.stack.append((tag, attributes))
        for attribute, marker in self._ATTRIBUTES.items():
            value = attributes.get(attribute) or ""
            if value.strip() and marker not in attributes:
                self.violations.append(
                    f"{self.rel}:{self.getpos()[0]}: {attribute} literal requires {marker}"
                )

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        text = " ".join(data.split())
        if not text or not any(character.isalpha() for character in text) or not self.stack:
            return
        tag, attributes = self.stack[-1]
        if tag in {"script", "style", "title"} or (len(text) == 1 and text.isupper()):
            return
        if "data-i18n" not in attributes:
            self.violations.append(
                f"{self.rel}:{self.getpos()[0]}: visible HTML literal requires data-i18n"
            )


def extension_locale_violations(
    extension_dir: Path | None = None, locale_name: str = "en",
) -> list[str]:
    """Validate extension key coverage, placeholders, and literal UI sinks."""
    extension_dir = extension_dir or EXTENSION_DIR
    violations: list[str] = []
    catalog_path = extension_dir / "_locales" / locale_name / "messages.json"
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"{catalog_path.as_posix()}:1: invalid extension locale catalog: {exc}"]

    required_substitutions: dict[str, int] = {}
    for key in sorted(extension_message_keys(extension_dir) - set(catalog)):
        violations.append(f"browser-extension:1: locale is missing key {key}")
    for key, value in sorted(catalog.items()):
        if not isinstance(value, dict) or not isinstance(value.get("message"), str) or not value["message"]:
            violations.append(f"{catalog_path.as_posix()}:1: {key} must have a non-empty message")
            continue
        tokens = {token.upper() for token in _EXTENSION_PLACEHOLDER.findall(value["message"])}
        placeholders = value.get("placeholders", {})
        if not isinstance(placeholders, dict):
            violations.append(f"{catalog_path.as_posix()}:1: {key} placeholders must be an object")
            continue
        declared = {str(name).upper() for name in placeholders}
        if tokens != declared:
            violations.append(
                f"{catalog_path.as_posix()}:1: {key} message placeholders "
                f"{sorted(tokens)} do not match declarations {sorted(declared)}"
            )
        for name, definition in placeholders.items():
            content = definition.get("content") if isinstance(definition, dict) else None
            if not isinstance(content, str) or not re.fullmatch(r"\$[1-9][0-9]*", content):
                violations.append(
                    f"{catalog_path.as_posix()}:1: {key}.{name} needs positional content such as $1"
                )
            else:
                required_substitutions[key] = max(
                    required_substitutions.get(key, 0), int(content[1:]),
                )

    for html_file in sorted(extension_dir.glob("*.html")):
        rel = html_file.relative_to(extension_dir.parent).as_posix()
        audit = _ExtensionHTMLAudit(rel)
        audit.feed(html_file.read_text(encoding="utf-8"))
        violations.extend(audit.violations)

    for js_file in sorted(extension_dir.glob("*.js")):
        rel = js_file.relative_to(extension_dir.parent).as_posix()
        source = js_file.read_text(encoding="utf-8")
        for match in _EXTENSION_MESSAGE_CALL.finditer(source):
            arguments = match.group(3).strip()
            provided = 0 if not arguments else arguments.count(",") + 1
            required = required_substitutions.get(match.group(2), 0)
            if provided < required:
                line_number = source.count("\n", 0, match.start()) + 1
                violations.append(
                    f"{rel}:{line_number}: {match.group(2)} needs {required} substitution(s), "
                    f"got {provided}"
                )
        for line_number, line in enumerate(source.splitlines(), 1):
            for match in _EXTENSION_UI_ASSIGNMENT.finditer(line):
                visible = re.sub(r"\$\{[^}]+\}", "", match.group(2))
                if len(visible) == 1 and visible.isupper():
                    continue
                if any(character.isalpha() for character in visible):
                    violations.append(
                        f"{rel}:{line_number}: extension UI assignment must use extensionMessage()"
                    )
    return violations


def localization_contract_violations() -> list[str]:
    """Return every deterministic localization contract violation."""
    return [
        *desktop_literal_violations(),
        *desktop_placeholder_violations(),
        *extension_locale_violations(),
    ]


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Generate or validate the Bookmark Organizer Pro gettext template.")
    parser.add_argument("--check", action="store_true", help="fail if locale/bop.pot is stale")
    args = parser.parse_args(argv)

    pot_path = POT_PATH
    if args.check:
        current = pot_is_current(pot_path)
        violations = localization_contract_violations()
        if current and not violations:
            print(f"{pot_path} is current")
            return 0
        for violation in violations:
            print(violation, file=sys.stderr)
        if not current:
            print(
                f"{pot_path} is stale; run `python -m bookmark_organizer_pro.i18n` and commit the result.",
                file=sys.stderr,
            )
        return 1

    count = write_pot(pot_path)
    print(f"Wrote {count} translatable strings to {pot_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
