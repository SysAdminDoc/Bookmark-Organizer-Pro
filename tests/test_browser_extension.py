"""Static checks for the bundled browser extension scaffold."""

import json
import re
import tempfile
import unittest
import urllib.error
import urllib.request
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

    def test_sidepanel_uses_paginated_recent_load_more(self):
        sidepanel_html = (EXT_DIR / "sidepanel.html").read_text(encoding="utf-8")
        sidepanel_js = (EXT_DIR / "sidepanel.js").read_text(encoding="utf-8")

        self.assertIn('id="loadMoreRecent"', sidepanel_html)
        self.assertIn("RECENT_PAGE_SIZE", sidepanel_js)
        self.assertIn("offset=${recentOffset}", sidepanel_js)
        self.assertIn("data.next_offset", sidepanel_js)
        self.assertIn("data.has_more", sidepanel_js)
        self.assertIn("append: true", sidepanel_js)

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


class TestBrowserExtensionApiRoundTrip(unittest.TestCase):
    def _make_manager(self, tmp: str):
        import main

        root = Path(tmp)
        return main.BookmarkManager(
            main.CategoryManager(filepath=root / "categories.json"),
            main.TagManager(filepath=root / "tags.json"),
            filepath=root / "bookmarks.json",
        )

    def _api_token(self) -> str:
        from bookmark_organizer_pro.services.api import _KEYRING_KEY, _KEYRING_SERVICE, _TOKEN_FILE

        if _TOKEN_FILE.exists():
            token = _TOKEN_FILE.read_text(encoding="utf-8").strip()
            if token:
                return token
        try:
            import keyring

            return keyring.get_password(_KEYRING_SERVICE, _KEYRING_KEY) or ""
        except Exception:
            return ""

    def _post_json(self, base_url: str, payload, token: str = ""):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = urllib.request.Request(
            f"{base_url}/bookmarks",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def test_extension_save_paths_round_trip_through_local_api(self):
        import main

        extension_payloads = [
            (
                "popup",
                {
                    "url": "https://example.com/popup-save",
                    "title": "Popup Save",
                    "category": "Research",
                    "tags": "ai, browser, ai",
                    "notes": "Selected: Popup passage",
                    "read_later": True,
                },
                {
                    "title": "Popup Save",
                    "category": "Research",
                    "tags": ["ai", "browser"],
                    "notes": "Selected: Popup passage",
                    "read_later": True,
                    "read_later_position": 0,
                },
            ),
            (
                "sidepanel_add",
                {
                    "url": "https://example.com/sidepanel-save",
                    "title": "Side Panel Save",
                    "category": "Development",
                    "tags": "extension, local",
                    "notes": "Saved from side panel",
                    "read_later": False,
                },
                {
                    "title": "Side Panel Save",
                    "category": "Development",
                    "tags": ["extension", "local"],
                    "notes": "Saved from side panel",
                    "read_later": False,
                },
            ),
            (
                "reading_list_import",
                {
                    "url": "https://example.com/reading-list",
                    "title": "Reading List Item",
                    "category": "Uncategorized / Needs Review",
                    "read_later": True,
                },
                {
                    "title": "Reading List Item",
                    "category": "Uncategorized / Needs Review",
                    "tags": [],
                    "notes": "",
                    "read_later": True,
                    "read_later_position": 1,
                },
            ),
            (
                "context_menu_quick_save",
                {
                    "url": "https://example.com/context-menu",
                    "title": "Context Menu Save",
                    "category": "Uncategorized / Needs Review",
                    "tags": [],
                    "notes": "Selected: Context passage",
                },
                {
                    "title": "Context Menu Save",
                    "category": "Uncategorized / Needs Review",
                    "tags": [],
                    "notes": "Selected: Context passage",
                    "read_later": False,
                },
            ),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            api = main.BookmarkAPI(manager, port=0)
            try:
                api.start()
                token = self._api_token()
                base_url = f"http://127.0.0.1:{api.port}"

                status, body = self._post_json(base_url, {"url": "https://example.com/unauthorized"})
                self.assertEqual(status, 401)
                self.assertIn("Unauthorized", body["error"])

                for label, payload, expected in extension_payloads:
                    with self.subTest(label=label):
                        status, body = self._post_json(base_url, payload, token=token)
                        self.assertEqual(status, 201)
                        self.assertEqual(body["url"], payload["url"])
                        for key, value in expected.items():
                            self.assertEqual(body[key], value)

                status, body = self._post_json(base_url, extension_payloads[0][1], token=token)
                self.assertEqual(status, 409)
                self.assertIn("exists", body["error"])

                status, body = self._post_json(base_url, {"url": "file:///tmp/not-saveable"}, token=token)
                self.assertEqual(status, 400)
                self.assertIn("http", body["error"])
            finally:
                api.stop()


if __name__ == "__main__":
    unittest.main()
