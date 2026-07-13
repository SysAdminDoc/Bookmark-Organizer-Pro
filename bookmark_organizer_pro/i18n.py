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
from pathlib import Path
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


def _(message: str) -> str:
    return _translation.gettext(message)


def N_(message: str) -> str:
    """Mark a deferred string for extraction without translating at import time."""
    return message


def ngettext(singular: str, plural: str, n: int) -> str:
    return _translation.ngettext(singular, plural, n)


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


def collect_translatable_strings(src_root: Path | None = None) -> dict[str, list[tuple[str, int]]]:
    """Scan gettext calls and recognizable UI literal arguments."""
    import ast

    src_root = src_root or Path(__file__).resolve().parent
    strings: dict[str, list[tuple[str, int]]] = {}

    for py_file in sorted(src_root.rglob("*.py")):
        rel = py_file.relative_to(src_root.parent).as_posix()
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(rel))
        except SyntaxError:
            continue
        is_ui_module = "/ui/" in f"/{rel}" or "/app_mixins/" in f"/{rel}"

        def add(value, line_number: int) -> None:
            if isinstance(value, ast.Constant) and isinstance(value.value, str) and value.value.strip():
                strings.setdefault(value.value, []).append((rel, line_number))

        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"_", "N_"}
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                add(node.args[0], node.lineno)
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "ngettext"
            ):
                for argument in node.args[:2]:
                    add(argument, node.lineno)

            if not is_ui_module or not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg in {"text", "label", "title", "message", "prompt"}:
                    add(keyword.value, node.lineno)
            method = node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if method == "title":
                for argument in node.args[:1]:
                    add(argument, node.lineno)
            elif method in {
                "showinfo", "showerror", "showwarning", "askyesno", "askokcancel",
            }:
                for argument in node.args[:2]:
                    add(argument, node.lineno)

    for locations in strings.values():
        locations.sort()

    return strings


def build_pot() -> str:
    """Build the gettext template contents from current source strings."""
    strings = collect_translatable_strings()

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

    return "\n".join(lines)


def write_pot(pot_path: Path | None = None) -> int:
    """Write ``locale/bop.pot`` and return the number of translatable strings."""
    strings = collect_translatable_strings()
    pot_path = pot_path or POT_PATH

    pot_path.parent.mkdir(parents=True, exist_ok=True)
    pot_path.write_text(build_pot(), encoding="utf-8")
    return len(strings)


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


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Generate or validate the Bookmark Organizer Pro gettext template.")
    parser.add_argument("--check", action="store_true", help="fail if locale/bop.pot is stale")
    args = parser.parse_args(argv)

    pot_path = POT_PATH
    if args.check:
        current = pot_is_current(pot_path)
        missing_extension = extension_missing_keys()
        if current and not missing_extension:
            print(f"{pot_path} is current")
            return 0
        if missing_extension:
            print(
                "Extension locale is missing keys: " + ", ".join(sorted(missing_extension)),
                file=sys.stderr,
            )
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
