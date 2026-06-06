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
import os
from pathlib import Path

_LOCALE_DIR = Path(__file__).resolve().parent.parent / "locale"
_DOMAIN = "bop"

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


def _generate_pot():
    """Scan source files and write ``locale/bop.pot``."""
    import ast
    import textwrap

    src_root = Path(__file__).resolve().parent
    strings: dict[str, list[str]] = {}

    for py_file in sorted(src_root.rglob("*.py")):
        rel = py_file.relative_to(src_root.parent)
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
                loc = f"{rel}:{node.lineno}"
                strings.setdefault(msg, []).append(loc)

    _LOCALE_DIR.mkdir(parents=True, exist_ok=True)
    pot_path = _LOCALE_DIR / f"{_DOMAIN}.pot"

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
        for loc in locations:
            lines.append(f"#: {loc}")
        escaped = msg.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        lines.append(f'msgid "{escaped}"')
        lines.append('msgstr ""')
        lines.append('')

    pot_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {len(strings)} translatable strings to {pot_path}")


if __name__ == "__main__":
    _generate_pot()
