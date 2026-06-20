"""Static checks for the bundled browser extension scaffold."""

import json
import re
import unittest
from pathlib import Path

from bookmark_organizer_pro.constants import APP_VERSION


ROOT = Path(__file__).resolve().parents[1]
EXT_DIR = ROOT / "browser-extension"


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
        spec_text = (ROOT / "packaging" / "bookmark_organizer.spec").read_text(encoding="utf-8")
        version_info = (ROOT / "packaging" / "version_info.txt").read_text(encoding="utf-8")

        self.assertRegex(pyproject_text, re.compile(rf'^version = "{re.escape(APP_VERSION)}"$', re.MULTILINE))
        self.assertEqual(manifest["version"], APP_VERSION)
        self.assertIn(f'APP_VERSION = "{APP_VERSION}"', spec_text)

        file_version = ".".join((*APP_VERSION.split("."), "0"))
        tuple_version = ", ".join((*APP_VERSION.split("."), "0"))
        self.assertIn(f"filevers=({tuple_version})", version_info)
        self.assertIn(f"prodvers=({tuple_version})", version_info)
        self.assertRegex(version_info, re.compile(rf"FileVersion'.*{re.escape(file_version)}"))
        self.assertRegex(version_info, re.compile(rf"ProductVersion'.*{re.escape(file_version)}"))


if __name__ == "__main__":
    unittest.main()
