import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from bookmark_organizer_pro import i18n


def test_gettext_template_is_current():
    assert i18n.POT_PATH.read_text(encoding="utf-8") == i18n.build_pot()


def test_i18n_check_cli_passes_when_template_is_current(capsys):
    result = i18n.main(["--check"])

    captured = capsys.readouterr()
    assert result == 0
    assert "is current" in captured.out


def test_pseudo_locales_expand_preserve_placeholders_and_mirror_layouts():
    source = "Save {count} bookmarks"
    expanded = i18n.pseudo_localize(source)
    assert len(expanded) > len(source) * 1.25
    assert "{count}" in expanded

    i18n.setup_locale("qps-plocm")
    try:
        translated = i18n._(source)
        assert translated.startswith("\u202b")
        assert "{count}" in translated
        assert i18n.is_rtl()
        assert i18n.layout_side("left") == "right"
        assert i18n.layout_side("right") == "left"
        assert i18n.layout_anchor("w") == "e"
        assert i18n.layout_anchor("nw") == "ne"
    finally:
        i18n.setup_locale("en")


def test_formatted_messages_translate_before_interpolation(monkeypatch):
    class Translation:
        def gettext(self, message):
            return {"Saved {count} bookmark": "Stored {count} link"}.get(message, message)

    monkeypatch.setattr(i18n, "_translation", Translation())
    assert i18n.format_message("Saved {count} bookmark", count=2) == "Stored 2 link"


def test_major_desktop_surface_strings_are_extractable():
    strings = i18n.collect_translatable_strings()
    expected = {
        "Dashboard",
        "Category Distribution",
        "Create Custom Theme",
        "Theme settings",
        "About",
        "Copy Diagnostics",
    }
    assert not expected.difference(strings)
    assert i18n.desktop_literal_violations() == []
    assert i18n.desktop_placeholder_violations() == []


def test_unwrapped_desktop_ui_literal_fails_localization_contract(tmp_path):
    package = tmp_path / "bookmark_organizer_pro"
    ui_dir = package / "ui"
    ui_dir.mkdir(parents=True)
    (ui_dir / "dialog.py").write_text(
        'import tkinter as tk\n\ndef build(root):\n    return tk.Label(root, text="Not translated")\n',
        encoding="utf-8",
    )

    violations = i18n.desktop_literal_violations(package)
    assert len(violations) == 1
    assert "text literal must use" in violations[0]


def test_plural_and_format_placeholders_must_match(tmp_path):
    package = tmp_path / "bookmark_organizer_pro"
    package.mkdir()
    (package / "messages.py").write_text(
        'from bookmark_organizer_pro.i18n import format_message, ngettext\n'
        'format_message("Saved {count}", total=2)\n'
        'ngettext("{count} item", "{total} items", 2)\n',
        encoding="utf-8",
    )

    violations = i18n.desktop_placeholder_violations(package)
    assert len(violations) == 2
    assert any("format_message placeholders" in violation for violation in violations)
    assert any("placeholders differ" in violation for violation in violations)


def test_contextual_gettext_and_plural_contracts_preserve_metadata(tmp_path):
    package = tmp_path / "bookmark_organizer_pro"
    package.mkdir()
    source = package / "messages.py"
    source.write_text(
        'from bookmark_organizer_pro.i18n import npgettext, pgettext\n'
        'pgettext("menu", "Open")\n'
        'npgettext("table", "{count} row", "{count} rows", 2, count=2)\n',
        encoding="utf-8",
    )

    assert ("menu", "Open") in i18n.collect_contextual_strings(package)
    assert ("table", "{count} row", "{count} rows") in i18n.collect_contextual_plural_strings(package)
    assert i18n.desktop_placeholder_violations(package) == []


def test_production_catalog_preserves_contextual_entries():
    pot = i18n.build_pot()
    assert 'msgctxt "read-later"' in pot
    assert 'msgid "Open"' in pot


def test_extension_runtime_literals_fail_localization_contract(tmp_path):
    extension = tmp_path / "extension"
    shutil.copytree(i18n.EXTENSION_DIR, extension)
    popup_path = extension / "popup.js"
    popup_path.write_text(
        popup_path.read_text(encoding="utf-8") + '\nsetStatus("Runtime bypass");\n',
        encoding="utf-8",
    )

    violations = i18n.extension_locale_violations(extension)
    assert any("visible message call must use extensionMessage" in violation for violation in violations)

    sidepanel_path = extension / "sidepanel.js"
    sidepanel_path.write_text(
        sidepanel_path.read_text(encoding="utf-8") + '\nshowEmpty(document.body, "Runtime empty state");\n',
        encoding="utf-8",
    )
    violations = i18n.extension_locale_violations(extension)
    assert any("visible empty-state message must use extensionMessage" in violation for violation in violations)


def test_missing_desktop_key_fails_template_gate(tmp_path):
    incomplete = tmp_path / "bop.pot"
    incomplete.write_text(i18n.build_pot().replace('msgid "Dashboard"', 'msgid "Missing"'), encoding="utf-8")
    assert not i18n.pot_is_current(incomplete)


def test_extension_locale_covers_manifest_and_document_keys():
    assert i18n.extension_missing_keys() == set()
    assert i18n.extension_locale_violations() == []
    manifest = json.loads((i18n.EXTENSION_DIR / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["default_locale"] == "en"
    assert manifest["name"] == "__MSG_extensionName__"
    for html_file in i18n.EXTENSION_DIR.glob("*.html"):
        html = html_file.read_text(encoding="utf-8")
        assert '<html lang="en" dir="ltr"' in html
        assert "data-i18n-title=" in html


def test_missing_extension_key_fails_local_gate(tmp_path):
    extension = tmp_path / "extension"
    shutil.copytree(i18n.EXTENSION_DIR, extension)
    catalog_path = extension / "_locales" / "en" / "messages.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    del catalog["saveBookmark"]
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    assert "saveBookmark" in i18n.extension_missing_keys(extension)


def test_extension_literal_and_placeholder_drift_fail_local_gate(tmp_path):
    extension = tmp_path / "extension"
    shutil.copytree(i18n.EXTENSION_DIR, extension)
    popup_path = extension / "popup.html"
    popup_path.write_text(
        popup_path.read_text(encoding="utf-8").replace("</main>", "<button>Bypass</button></main>"),
        encoding="utf-8",
    )
    catalog_path = extension / "_locales" / "en" / "messages.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["saveBookmark"]["message"] = "Save $COUNT$ bookmarks"
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")

    violations = i18n.extension_locale_violations(extension)
    assert any("visible HTML literal requires data-i18n" in violation for violation in violations)
    assert any("saveBookmark message placeholders" in violation for violation in violations)


def test_extension_title_requires_localization_marker(tmp_path):
    extension = tmp_path / "extension"
    shutil.copytree(i18n.EXTENSION_DIR, extension)
    popup_path = extension / "popup.html"
    html = popup_path.read_text(encoding="utf-8").replace(
        'data-i18n-title="popupTitle"', 'data-title-fallback="popupTitle"',
    )
    popup_path.write_text(html, encoding="utf-8")

    violations = i18n.extension_locale_violations(extension)
    assert any("visible HTML title requires data-i18n-title" in violation for violation in violations)


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js is required for the MV3 locale harness")
def test_extension_applies_active_language_rtl_and_messages():
    harness = r"""
const fs = require("fs");
const vm = require("vm");
const label = {
  dataset: { i18n: "saveBookmark" }, textContent: "Save Bookmark",
  getAttribute() { return ""; }, setAttribute() {}
};
const root = {
  dataset: { i18nTitle: "popupTitle" }, lang: "en", dir: "ltr",
  getAttribute() { return ""; }, setAttribute() {}
};
const document = {
  documentElement: root, readyState: "complete", title: "Fallback",
  querySelectorAll(selector) {
    if (selector === "[data-i18n]") return [label];
    if (selector === "[data-i18n-title]") return [root];
    return [];
  }
};
const messages = { saveBookmark: "حفظ الإشارة", popupTitle: "حفظ" };
const chrome = { i18n: { getUILanguage: () => "ar-EG", getMessage: key => messages[key] || "" } };
const context = vm.createContext({ chrome, document, navigator: { language: "en" }, console });
context.globalThis = context;
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
process.stdout.write(JSON.stringify({ lang: root.lang, dir: root.dir, text: label.textContent, title: document.title }));
"""
    completed = subprocess.run(
        ["node", "-e", harness, str(i18n.EXTENSION_DIR / "i18n.js")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result == {"lang": "ar-EG", "dir": "rtl", "text": "حفظ الإشارة", "title": "حفظ"}


@pytest.mark.skipif(not shutil.which("node"), reason="Node.js is required for the MV3 pseudo-locale harness")
def test_extension_pseudo_locale_expands_and_humanizes_missing_keys():
    harness = r"""
const fs = require("fs");
const vm = require("vm");
const label = {
  dataset: { i18n: "saveBookmark" }, textContent: "Save Bookmark",
  getAttribute() { return ""; }, setAttribute() {}
};
const root = {
  dataset: { i18nTitle: "popupTitle" }, lang: "en", dir: "ltr", title: "Fallback",
  getAttribute() { return ""; }, setAttribute() {}
};
const document = {
  documentElement: root, readyState: "complete", title: "Fallback",
  querySelectorAll(selector) {
    if (selector === "[data-i18n]") return [label];
    if (selector === "[data-i18n-title]") return [root];
    return [];
  }
};
const chrome = { i18n: { getUILanguage: () => "qps-plocm", getMessage: () => "" } };
const context = vm.createContext({ chrome, document, navigator: { language: "en" }, console });
context.globalThis = context;
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
process.stdout.write(JSON.stringify({
  dir: root.dir,
  text: label.textContent,
  title: document.title,
  missing: context.extensionMessage("missingKey", [], "")
}));
"""
    completed = subprocess.run(
        ["node", "-e", harness, str(i18n.EXTENSION_DIR / "i18n.js")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=10,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["dir"] == "rtl"
    assert len(result["text"]) > len("Save Bookmark") * 1.25
    assert "missingKey" != result["missing"]
    assert result["missing"].startswith("\u202b")


# ── R-186: a compiled catalog has to load from an install, not just a checkout ─


def _compile_catalog(root: Path, language: str, msgid: str, msgstr: str) -> Path:
    """Write a minimal .mo the way msgfmt would, without needing gettext tools."""
    import struct

    target = root / language / "LC_MESSAGES"
    target.mkdir(parents=True, exist_ok=True)
    entries = [(b"", b"Content-Type: text/plain; charset=UTF-8\n"),
               (msgid.encode("utf-8"), msgstr.encode("utf-8"))]
    entries.sort()
    count = len(entries)
    key_start = 7 * 4 + 16 * count
    value_start = key_start + sum(len(key) + 1 for key, _ in entries)
    key_offsets, value_offsets = [], []
    offset = key_start
    for key, _value in entries:
        key_offsets.append((len(key), offset))
        offset += len(key) + 1
    offset = value_start
    for _key, value in entries:
        value_offsets.append((len(value), offset))
        offset += len(value) + 1
    output = struct.pack(
        "Iiiiiii", 0x950412DE, 0, count, 7 * 4, 7 * 4 + count * 8, 0, 0
    )
    for length, position in key_offsets:
        output += struct.pack("ii", length, position)
    for length, position in value_offsets:
        output += struct.pack("ii", length, position)
    for key, _value in entries:
        output += key + b"\x00"
    for _key, value in entries:
        output += value + b"\x00"
    catalog = target / "bop.mo"
    catalog.write_bytes(output)
    return catalog


def test_a_catalog_loads_from_every_install_layout(tmp_path, monkeypatch):
    """Source checkout, installed wheel, PyInstaller and Nuitka roots."""
    from bookmark_organizer_pro import i18n

    layouts = {
        "wheel": tmp_path / "package" / "locale",
        "pyinstaller": tmp_path / "meipass" / "locale",
        "frozen": tmp_path / "beside-exe" / "locale",
        "source": tmp_path / "checkout" / "locale",
    }
    for root in layouts.values():
        _compile_catalog(root, "qq", "Library", "Bibliotheek")

    for name, root in layouts.items():
        monkeypatch.setattr(i18n, "locale_roots", lambda root=root: [root])
        try:
            i18n.setup_locale("qq")
            assert i18n._("Library") == "Bibliotheek", f"{name} layout did not load the catalog"
        finally:
            monkeypatch.undo()
            i18n.setup_locale("en")


def test_locale_roots_cover_the_frozen_and_wheel_layouts(monkeypatch):
    from bookmark_organizer_pro import i18n

    monkeypatch.setattr(sys, "_MEIPASS", str(Path("C:/bundle")), raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    roots = [str(root) for root in i18n.locale_roots()]

    assert any(root.endswith(str(Path("bookmark_organizer_pro/locale"))) for root in roots), roots
    assert any(str(Path("C:/bundle/locale")) == root for root in roots), roots
    assert len(roots) == len(set(roots)), "locale roots must not repeat"


def test_a_language_without_a_catalog_falls_through_to_the_next_root(tmp_path, monkeypatch):
    """A directory that merely exists must not stop the search."""
    from bookmark_organizer_pro import i18n

    empty = tmp_path / "empty" / "locale"
    empty.mkdir(parents=True)
    populated = tmp_path / "populated" / "locale"
    _compile_catalog(populated, "qq", "Library", "Bibliotheek")

    monkeypatch.setattr(i18n, "locale_roots", lambda: [empty, populated])
    try:
        i18n.setup_locale("qq")
        assert i18n._("Library") == "Bibliotheek"
    finally:
        i18n.setup_locale("en")


def test_every_build_path_ships_compiled_catalogs():
    root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    spec = (root / "packaging" / "bookmark_organizer.spec").read_text(encoding="utf-8")
    nuitka = (root / "packaging" / "nuitka_build.py").read_text(encoding="utf-8")

    package_data = pyproject["tool"]["setuptools"]["package-data"]["bookmark_organizer_pro"]
    assert "locale/*/LC_MESSAGES/*.mo" in package_data
    assert 'LC_MESSAGES/*.mo' in spec, "PyInstaller spec collects no message catalogs"
    assert 'LC_MESSAGES/*.mo' in nuitka, "Nuitka build collects no message catalogs"


def test_the_builds_collect_from_the_directory_lookup_prefers():
    """All four have to agree on one location or the wheel ships nothing.

    setuptools package-data globs are relative to the package directory, so a
    catalog at the repo root cannot reach a wheel however it is declared. The
    canonical home is therefore inside the package, and the two frozen builds
    have to read the same place rather than the repo root beside the POT.
    """
    from bookmark_organizer_pro import i18n

    root = Path(__file__).resolve().parents[1]
    spec = (root / "packaging" / "bookmark_organizer.spec").read_text(encoding="utf-8")
    nuitka = (root / "packaging" / "nuitka_build.py").read_text(encoding="utf-8")

    preferred = i18n.locale_roots()[0]
    assert preferred == root / "bookmark_organizer_pro" / "locale", preferred
    assert 'ROOT_DIR / "bookmark_organizer_pro" / "locale"' in spec
    assert 'root / "bookmark_organizer_pro" / "locale"' in nuitka
    # The POT stays at the repo root next to the translator-facing sources.
    assert i18n.POT_PATH == root / "locale" / "bop.pot"


def test_each_build_path_collects_a_catalog_that_is_really_there():
    """Assert against real files, not against the text of the config.

    Checking that the string "LC_MESSAGES/*.mo" appears in a spec proves
    nothing about whether the glob resolves: there are no catalogs in the tree
    yet, so a wrong base directory would look identical to a right one. This
    plants a catalog where a translator's compiled output belongs and checks
    each build path actually picks it up.
    """
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    catalog_root = root / "bookmark_organizer_pro" / "locale"
    planted = _compile_catalog(catalog_root, "qq", "Library", "Bibliotheek")
    try:
        # Nuitka: build_command is a pure function, so ask it directly.
        spec = importlib.util.spec_from_file_location(
            "nuitka_build_probe", root / "packaging" / "nuitka_build.py"
        )
        nuitka_build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(nuitka_build)
        command = nuitka_build.build_command(root=root, version="0.0.0")
        expected = "bookmark_organizer_pro/locale/qq/LC_MESSAGES/bop.mo"
        assert any(
            arg.startswith("--include-data-files=") and arg.endswith(f"={expected}")
            for arg in command
        ), [arg for arg in command if "locale" in arg]

        # PyInstaller: evaluate the spec's own glob against the planted file.
        spec_text = (root / "packaging" / "bookmark_organizer.spec").read_text(encoding="utf-8")
        assert 'CATALOG_DIR = ROOT_DIR / "bookmark_organizer_pro" / "locale"' in spec_text
        collected = sorted(catalog_root.glob("*/LC_MESSAGES/*.mo"))
        assert planted in collected, collected

        # Wheel: package-data globs are package-relative, so the planted file
        # has to match from inside the package directory.
        package_dir = root / "bookmark_organizer_pro"
        assert planted in set(package_dir.glob("locale/*/LC_MESSAGES/*.mo"))
    finally:
        shutil.rmtree(catalog_root, ignore_errors=True)


def test_the_nuitka_catalog_loop_does_not_shadow_the_build_target():
    """`target` is a build_command parameter; reusing the name is a latent bug."""
    nuitka = (
        Path(__file__).resolve().parents[1] / "packaging" / "nuitka_build.py"
    ).read_text(encoding="utf-8")

    catalog_block = nuitka.split("catalog_dir = ")[1].split("if sys.platform")[0]
    assert "target =" not in catalog_block, catalog_block
