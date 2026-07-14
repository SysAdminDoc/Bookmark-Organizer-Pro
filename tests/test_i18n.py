import json
import shutil
import subprocess

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
