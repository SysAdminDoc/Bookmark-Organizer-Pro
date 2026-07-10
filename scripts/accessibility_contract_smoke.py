"""Local accessibility contract checks for extension and Tk control surfaces."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

EXTENSION_FILES = ("popup.html", "options.html", "sidepanel.html")
INTERACTIVE_TAGS = {"button", "input", "select", "textarea"}
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


@dataclass
class Element:
    tag: str
    attrs: dict[str, str]
    text: str = ""

    def attr(self, name: str) -> str:
        return self.attrs.get(name, "").strip()


class AccessibilityContractError(AssertionError):
    """Raised when a local accessibility contract check fails."""


class ContractHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: list[Element] = []
        self._stack: list[Element] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        attr_map = {str(name).lower(): str(value or "") for name, value in attrs}
        if any(parent.tag == "label" for parent in self._stack):
            attr_map["__wrapped_label"] = "1"
        if self._stack:
            attr_map["__parent_tag"] = self._stack[-1].tag
        element = Element(tag, attr_map)
        self.elements.append(element)
        if tag not in VOID_TAGS:
            self._stack.append(element)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        while self._stack:
            current = self._stack.pop()
            if current.tag == tag:
                break

    def handle_data(self, data: str) -> None:
        if not self._stack:
            return
        text = " ".join(data.split())
        if text:
            self._stack[-1].text = f"{self._stack[-1].text} {text}".strip()


def parse_html(path: Path) -> list[Element]:
    parser = ContractHTMLParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.elements


def element_id_map(elements: list[Element]) -> dict[str, Element]:
    return {element.attr("id"): element for element in elements if element.attr("id")}


def text_for_labelledby(element: Element, ids: dict[str, Element]) -> str:
    parts: list[str] = []
    for ref in element.attr("aria-labelledby").split():
        if ref in ids:
            parts.append(ids[ref].text)
    return " ".join(part for part in parts if part).strip()


def has_accessible_name(element: Element, ids: dict[str, Element], label_controls: set[str]) -> bool:
    if element.text.strip():
        return True
    if element.attr("aria-label"):
        return True
    if text_for_labelledby(element, ids):
        return True
    if element.attr("title"):
        return True
    control_id = element.attr("id")
    return bool(control_id and control_id in label_controls)


def explicit_and_wrapped_label_targets(elements: list[Element]) -> set[str]:
    targets: set[str] = set()
    for element in elements:
        if element.tag == "label":
            target = element.attr("for")
            if target:
                targets.add(target)
            continue
        if element.attr("__wrapped_label") and element.tag in {"input", "select", "textarea"} and element.attr("id"):
            targets.add(element.attr("id"))
    return targets


def check_extension_file(path: Path) -> dict[str, object]:
    elements = parse_html(path)
    ids = element_id_map(elements)
    label_controls = explicit_and_wrapped_label_targets(elements)
    failures: list[str] = []

    html = next((element for element in elements if element.tag == "html"), None)
    if not html or html.attr("lang") != "en":
        failures.append("html element must declare lang=\"en\"")

    if not any(element.tag == "main" for element in elements):
        failures.append("page must expose a main landmark")

    title = next((element for element in elements if element.tag == "title"), None)
    if not title or not title.text:
        failures.append("page must include a non-empty title")

    for element in elements:
        role = element.attr("role")
        if element.tag in INTERACTIVE_TAGS and not has_accessible_name(element, ids, label_controls):
            failures.append(f"{element.tag}#{element.attr('id') or '<no-id>'} has no accessible name")
        if role == "status" and element.attr("aria-live") not in {"polite", "assertive"}:
            failures.append(f"status region #{element.attr('id') or '<no-id>'} must declare aria-live")
        if element.attr("__parent_tag") == "ul" and element.tag != "li":
            failures.append(f"ul must contain li children, found {element.tag}")

    if path.name == "sidepanel.html":
        options = ids.get("openOptions")
        recent = ids.get("recentList")
        if not options:
            failures.append("side panel must expose an Options recovery action")
        if not recent or recent.attr("aria-busy") not in {"true", "false"}:
            failures.append("recent list must expose an aria-busy loading state")

    tablists = [element for element in elements if element.attr("role") == "tablist"]
    for tablist in tablists:
        if not has_accessible_name(tablist, ids, set()):
            failures.append("tablist must have an accessible name")

    tabs = [element for element in elements if element.attr("role") == "tab"]
    panels = [element for element in elements if element.attr("role") == "tabpanel"]
    if tabs or panels:
        tab_controls = {tab.attr("aria-controls") for tab in tabs}
        panel_ids = {panel.attr("id") for panel in panels}
        selected = [tab for tab in tabs if tab.attr("aria-selected") == "true"]
        if len(selected) != 1:
            failures.append("exactly one tab must be aria-selected=true")
        if tab_controls != panel_ids:
            failures.append("tab aria-controls values must match tabpanel ids")
        for panel in panels:
            label_id = panel.attr("aria-labelledby")
            if label_id not in ids:
                failures.append(f"tabpanel #{panel.attr('id')} must reference an existing tab")

    if failures:
        raise AccessibilityContractError(f"{path.name} accessibility failures: " + "; ".join(failures))
    return {"file": path.name, "elements": len(elements), "interactive": sum(1 for e in elements if e.tag in INTERACTIVE_TAGS)}


def check_extension_css(path: Path) -> dict[str, object]:
    css = path.read_text(encoding="utf-8")
    failures = []
    if "@media (prefers-reduced-motion: reduce)" not in css:
        failures.append("extension CSS must respect reduced motion")
    if "--bg: #0c1a29" not in css or "--accent: #19c7b5" not in css:
        failures.append("extension dark tokens must match Studio Dark")
    if failures:
        raise AccessibilityContractError(f"{path.name} accessibility failures: " + "; ".join(failures))
    return {"file": path.name, "reduced_motion": True, "studio_tokens": True}


def check_tk_interactions() -> dict[str, object]:
    import tkinter as tk

    from bookmark_organizer_pro.ui.tk_interactions import make_keyboard_activatable
    from bookmark_organizer_pro.ui.widget_controls import ModernButton

    if os.name == "nt":
        try:
            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    with tempfile.TemporaryDirectory(prefix="bop-a11y-data-", ignore_cleanup_errors=True) as data_dir:
        os.environ["BOOKMARK_DATA_DIR"] = data_dir
        root = tk.Tk()
        root.geometry("320x140+40+40")
        root.title("Bookmark Organizer Pro Accessibility Smoke")
        root.update()
        activations: list[str] = []
        try:
            label = tk.Label(root, text="Clear")
            label.pack(padx=8, pady=8)
            make_keyboard_activatable(label, lambda: activations.append("label"))
            root.update()
            label.focus_force()
            root.update()
            label.event_generate("<Return>", when="tail")
            label.event_generate("<space>", when="tail")
            root.update()
            if label.cget("takefocus") not in {1, "1"}:
                raise AccessibilityContractError("make_keyboard_activatable must set takefocus=1")
            for sequence in ("<Return>", "<KP_Enter>", "<space>"):
                if not label.bind(sequence):
                    raise AccessibilityContractError(f"keyboard activatable label missing {sequence} binding")
            if len(activations) < 2:
                raise AccessibilityContractError("keyboard activatable label did not invoke on Return and Space")

            button_hits: list[str] = []
            button = ModernButton(root, text="Run", command=lambda: button_hits.append("button"))
            button.pack()
            root.update()
            if button.cget("takefocus") not in {1, "1"}:
                raise AccessibilityContractError("ModernButton must be focusable")
            for sequence in ("<Return>", "<KP_Enter>", "<space>"):
                if not button.bind(sequence):
                    raise AccessibilityContractError(f"ModernButton missing {sequence} binding")
            button.set_state("disabled")
            root.update()
            if button.cget("takefocus") not in {0, "0"}:
                raise AccessibilityContractError("disabled ModernButton must leave the tab order")
            button.set_state("normal")
            return {"focusable_label": True, "modern_button": True}
        finally:
            root.destroy()


def run_checks() -> dict[str, object]:
    extension_dir = ROOT / "browser-extension"
    return {
        "extension": [check_extension_file(extension_dir / name) for name in EXTENSION_FILES],
        "extension_css": check_extension_css(extension_dir / "popup.css"),
        "tk": check_tk_interactions(),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run local accessibility contract checks.")
    parser.parse_args(argv)
    try:
        print(json.dumps(run_checks(), indent=2))
        return 0
    except AccessibilityContractError as exc:
        print(f"accessibility contract failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
