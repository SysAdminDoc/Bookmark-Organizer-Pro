"""Static checks for the bundled browser extension scaffold."""

import json
import re
import unittest
from pathlib import Path

from bookmark_organizer_pro.constants import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]
EXT_DIR = ROOT / "browser-extension"


def extract_js_object_literal(source: str, marker: str) -> str:
    """Return the object literal that starts after marker."""
    marker_index = source.index(marker)
    start = source.index("{", marker_index)
    depth = 0
    quote = ""
    escaped = False
    for index in range(start, len(source)):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in {"'", '"', "`"}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"Object literal not found after marker: {marker}")


class TestBrowserExtensionManifest(unittest.TestCase):
    def test_manifest_declares_mv3_popup_and_permissions(self):
        manifest = json.loads((EXT_DIR / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["manifest_version"], 3)
        self.assertEqual(manifest["version"], APP_VERSION)
        self.assertEqual(manifest["action"]["default_popup"], "popup.html")
        self.assertEqual(manifest["options_page"], "options.html")
        self.assertIn("activeTab", manifest["permissions"])
        self.assertIn("scripting", manifest["permissions"])
        self.assertIn("storage", manifest["permissions"])
        self.assertIn("http://127.0.0.1/*", manifest["host_permissions"])

    def test_popup_posts_to_local_bookmark_api_with_bearer_token(self):
        popup_js = (EXT_DIR / "popup.js").read_text(encoding="utf-8")
        shared_js = (EXT_DIR / "shared.js").read_text(encoding="utf-8")
        combined = shared_js + "\n" + popup_js

        self.assertIn("baseUrl(", popup_js)
        self.assertIn("/bookmarks", popup_js)
        self.assertIn("http://127.0.0.1:", shared_js)
        self.assertIn("Bearer", shared_js)
        self.assertIn('"Content-Type": "application/json"', shared_js)
        self.assertIn("api.scripting.executeScript", shared_js)
        self.assertNotIn("apiToken: \"secret", combined)

    def test_options_persists_port_token_and_default_category(self):
        options_js = (EXT_DIR / "options.js").read_text(encoding="utf-8")

        self.assertIn("apiPort", options_js)
        self.assertIn("apiToken", options_js)
        self.assertIn("defaultCategory", options_js)
        self.assertIn("storageSet({ apiPort: port, apiToken, defaultCategory })", options_js)

    def test_manifest_declares_sidepanel(self):
        manifest = json.loads((EXT_DIR / "manifest.json").read_text(encoding="utf-8"))

        self.assertIn("sidePanel", manifest["permissions"])
        self.assertEqual(manifest["side_panel"]["default_path"], "sidepanel.html")

    def test_sidepanel_fetches_bookmarks_with_auth(self):
        sp_js = (EXT_DIR / "sidepanel.js").read_text(encoding="utf-8")
        shared_js = (EXT_DIR / "shared.js").read_text(encoding="utf-8")

        self.assertIn("/bookmarks", sp_js)
        self.assertIn("/search?q=", sp_js)
        self.assertIn("Bearer", shared_js)

    def test_extension_save_payloads_include_read_later_state(self):
        popup_js = (EXT_DIR / "popup.js").read_text(encoding="utf-8")
        sidepanel_js = (EXT_DIR / "sidepanel.js").read_text(encoding="utf-8")

        self.assertIn('read_later: document.getElementById("readLater").checked', popup_js)
        self.assertIn('read_later: document.getElementById("addReadLater").checked', sidepanel_js)
        self.assertIn("read_later: !item.hasBeenRead", sidepanel_js)

    def test_popup_save_payload_contract_maps_form_fields(self):
        popup_js = (EXT_DIR / "popup.js").read_text(encoding="utf-8")
        payload = extract_js_object_literal(popup_js, "const payload =")

        self.assertIn("url: activeTab.url", payload)
        self.assertIn("title: activeTab.title || activeTab.url", payload)
        self.assertIn('category: document.getElementById("category").value.trim() || values.defaultCategory', payload)
        self.assertIn('tags: document.getElementById("tags").value', payload)
        self.assertIn('notes: document.getElementById("notes").value', payload)
        self.assertIn('read_later: document.getElementById("readLater").checked', payload)

    def test_sidepanel_save_payload_contract_maps_form_fields(self):
        sidepanel_js = (EXT_DIR / "sidepanel.js").read_text(encoding="utf-8")
        payload = extract_js_object_literal(sidepanel_js, "const payload =")

        self.assertIn("url,", payload)
        self.assertIn("title: titleEl.dataset.tabTitle || url", payload)
        self.assertIn('category: document.getElementById("addCategory").value.trim() || config.defaultCategory', payload)
        self.assertIn('tags: document.getElementById("addTags").value', payload)
        self.assertIn('notes: document.getElementById("addNotes").value', payload)
        self.assertIn('read_later: document.getElementById("addReadLater").checked', payload)

    def test_reading_list_import_payload_contract_maps_read_state(self):
        sidepanel_js = (EXT_DIR / "sidepanel.js").read_text(encoding="utf-8")
        payload = extract_js_object_literal(sidepanel_js, "body: JSON.stringify({")

        self.assertIn("url: item.url", payload)
        self.assertIn("title: item.title || item.url", payload)
        self.assertIn("category: config.defaultCategory", payload)
        self.assertIn("read_later: !item.hasBeenRead", payload)

    def test_background_quick_save_payload_contract_maps_context_fields(self):
        background_js = (EXT_DIR / "background.js").read_text(encoding="utf-8")
        payload = extract_js_object_literal(background_js, "body: JSON.stringify({")

        self.assertIn("url,", payload)
        self.assertIn("title: title || url", payload)
        self.assertIn("category: values.defaultCategory", payload)
        self.assertIn("tags: []", payload)
        self.assertIn('notes: notes || ""', payload)

    def test_extension_assets_exist(self):
        for name in [
            "manifest.json",
            "popup.html",
            "popup.js",
            "popup.css",
            "options.html",
            "options.js",
            "shared.js",
            "sidepanel.html",
            "sidepanel.js",
        ]:
            self.assertTrue((EXT_DIR / name).is_file(), name)

    def test_release_metadata_versions_match_app_version(self):
        pyproject_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        manifest = json.loads((EXT_DIR / "manifest.json").read_text(encoding="utf-8"))
        main_text = (ROOT / "main.py").read_text(encoding="utf-8")
        spec_text = (ROOT / "packaging" / "bookmark_organizer.spec").read_text(encoding="utf-8")
        version_info = (ROOT / "packaging" / "version_info.txt").read_text(encoding="utf-8")

        self.assertRegex(pyproject_text, re.compile(rf'^version = "{re.escape(APP_VERSION)}"$', re.MULTILINE))
        self.assertEqual(manifest["version"], APP_VERSION)
        self.assertIn(f'BOOTSTRAP_APP_VERSION = "{APP_VERSION}"', main_text)
        self.assertIn(f'APP_VERSION = "{APP_VERSION}"', spec_text)

        file_version = ".".join((*APP_VERSION.split("."), "0"))
        tuple_version = ", ".join((*APP_VERSION.split("."), "0"))
        self.assertIn(f"filevers=({tuple_version})", version_info)
        self.assertIn(f"prodvers=({tuple_version})", version_info)
        self.assertRegex(version_info, re.compile(rf"FileVersion'.*{re.escape(file_version)}"))
        self.assertRegex(version_info, re.compile(rf"ProductVersion'.*{re.escape(file_version)}"))


if __name__ == "__main__":
    unittest.main()
