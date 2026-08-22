"""Product copy helpers that do not depend on any UI toolkit.

`ui/foundation.py` is Tkinter-free, but importing anything from it executes
`bookmark_organizer_pro.ui.__init__`, which pulls in dialog modules. The CLI
and the command stack need correct plurals without that, so the two helpers
live here and `ui.foundation` re-exports them.
"""

from __future__ import annotations

from typing import Optional


def plural_of(singular: str) -> str:
    """Regular English plural for the nouns this product shows.

    Appending a bare "s" produced "51 categorys" in the export dialog.
    """
    word = str(singular or "")
    if not word:
        return word
    lowered = word.lower()
    if lowered.endswith("y") and len(word) > 1 and word[-2].lower() not in "aeiou":
        return word[:-1] + "ies"
    if lowered.endswith(("s", "x", "z", "ch", "sh")):
        return word + "es"
    return word + "s"


def pluralize(count: int, singular: str, plural: Optional[str] = None) -> str:
    """Return a count with a correctly pluralized label for product copy."""
    return f"{count} {singular if count == 1 else (plural or plural_of(singular))}"
