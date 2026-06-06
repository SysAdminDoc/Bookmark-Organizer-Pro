"""Static checks for the bundled browser extension scaffold."""

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXT_DIR = ROOT / "browser-extension"


class TestBrowserExtensionManifest(unittest.TestCase):
    def test_manifest_declares_mv3_popup_and_permissions(self):
        manifest = json.loads((EXT_DIR / "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["manifest_version"], 3)
        self.assertEqual(manifest["version"], "6.4.2")
        self.assertEqual(manifest["action"]["default_popup"], "popup.html")
        self.assertEqual(manifest["options_page"], "options.html")
        self.assertIn("activeTab", manifest["permissions"])
        self.assertIn("scripting", manifest["permissions"])
        self.assertIn("storage", manifest["permissions"])
        self.assertIn("http://127.0.0.1/*", manifest["host_permissions"])

    def test_popup_posts_to_local_bookmark_api_with_bearer_token(self):
        popup_js = (EXT_DIR / "popup.js").read_text(encoding="utf-8")

        self.assertIn("fetch(`http://127.0.0.1:${values.apiPort}/bookmarks`", popup_js)
        self.assertIn('"Authorization": `Bearer ${values.apiToken}`', popup_js)
        self.assertIn('"Content-Type": "application/json"', popup_js)
        self.assertIn("api.scripting.executeScript", popup_js)
        self.assertNotIn("apiToken: \"secret", popup_js)

    def test_options_persists_port_token_and_default_category(self):
        options_js = (EXT_DIR / "options.js").read_text(encoding="utf-8")

        self.assertIn("apiPort", options_js)
        self.assertIn("apiToken", options_js)
        self.assertIn("defaultCategory", options_js)
        self.assertIn("storageSet({ apiPort: port, apiToken, defaultCategory })", options_js)

    def test_extension_assets_exist(self):
        for name in [
            "manifest.json",
            "popup.html",
            "popup.js",
            "popup.css",
            "options.html",
            "options.js",
        ]:
            self.assertTrue((EXT_DIR / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
