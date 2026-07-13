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


def test_missing_desktop_key_fails_template_gate(tmp_path):
    incomplete = tmp_path / "bop.pot"
    incomplete.write_text(i18n.build_pot().replace('msgid "Dashboard"', 'msgid "Missing"'), encoding="utf-8")
    assert not i18n.pot_is_current(incomplete)


def test_extension_locale_covers_manifest_and_document_keys():
    assert i18n.extension_missing_keys() == set()
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
