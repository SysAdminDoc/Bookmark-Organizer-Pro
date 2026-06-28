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
import locale
import sys
from pathlib import Path
from typing import Sequence

_LOCALE_DIR = Path(__file__).resolve().parent.parent / "locale"
_DOMAIN = "bop"
POT_PATH = _LOCALE_DIR / f"{_DOMAIN}.pot"

_translation: gettext.GNUTranslations | gettext.NullTranslations = gettext.NullTranslations()


def _(message: str) -> str:
    return _translation.gettext(message)


def ngettext(singular: str, plural: str, n: int) -> str:
    return _translation.ngettext(singular, plural, n)


def setup_locale(lang: str = ""):
    """Initialize translations for *lang* (or the system default).

    Call once at app startup. Safe to call multiple times — later calls
    replace the active translation.
    """
    global _translation
    if not lang:
        lang = locale.getdefaultlocale()[0] or "en"

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
    """Scan Python source files for direct ``_("...")`` calls."""
    import ast

    src_root = src_root or Path(__file__).resolve().parent
    strings: dict[str, list[tuple[str, int]]] = {}

    for py_file in sorted(src_root.rglob("*.py")):
        rel = py_file.relative_to(src_root.parent).as_posix()
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(rel))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                msg = node.args[0].value
                strings.setdefault(msg, []).append((rel, node.lineno))

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


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Generate or validate the Bookmark Organizer Pro gettext template.")
    parser.add_argument("--check", action="store_true", help="fail if locale/bop.pot is stale")
    args = parser.parse_args(argv)

    pot_path = POT_PATH
    if args.check:
        if pot_is_current(pot_path):
            print(f"{pot_path} is current")
            return 0
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
