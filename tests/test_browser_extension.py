"""Static checks for the bundled browser extension scaffold."""

import concurrent.futures
import http.server
import importlib.util
import json
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

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

        self.assertIn("baseUrl(", shared_js)
        self.assertIn("saveBookmarkPayload", popup_js)
        self.assertIn("/bookmarks", shared_js)
        self.assertIn("http://127.0.0.1:", shared_js)
        self.assertIn("Bearer", shared_js)
        self.assertIn('"Content-Type": "application/json"', shared_js)
        self.assertIn("api.scripting.executeScript", shared_js)
        self.assertNotIn("apiToken: \"secret", combined)

    def test_options_persists_public_settings_and_delegates_token_to_background(self):
        options_js = (EXT_DIR / "options.js").read_text(encoding="utf-8")
        options_html = (EXT_DIR / "options.html").read_text(encoding="utf-8")
        shared_js = (EXT_DIR / "shared.js").read_text(encoding="utf-8")

        self.assertIn("apiPort", options_js)
        self.assertIn("apiToken", options_js)
        self.assertIn("defaultCategory", options_js)
        self.assertIn("storageSet({ apiPort: port, defaultCategory })", options_js)
        self.assertIn('{ type: "bop:set-api-token", apiToken }', options_js)
        self.assertNotIn("storageSet({ apiPort: port, apiToken", options_js)
        self.assertIn("pairExtension", options_js)
        self.assertIn('id="replacePairing"', options_html)
        self.assertIn('`${baseUrl(config)}/extension/pair`', shared_js)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for the pairing client harness")
    def test_shared_pairing_client_sends_explicit_rotation_contract(self):
        harness = r"""
const fs = require("fs");
const vm = require("vm");
const calls = [];
const chrome = {
  storage: { local: { get: async values => values, set: async () => {} } },
  runtime: { sendMessage: async () => ({}), getURL: path => path }
};
const context = vm.createContext({
  chrome,
  console,
  fetch: async (url, options) => {
    calls.push({ url, options });
    return { status: 200, json: async () => ({ paired: true }) };
  }
});
context.globalThis = context;
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
vm.runInContext(`(async () => {
  globalThis.result = await pairExtension({ apiPort: 9876, apiToken: "secret" }, { replace: true });
})()`, context).then(() => {
  process.stdout.write(JSON.stringify({ calls, result: context.result }));
});
"""
        completed = subprocess.run(
            ["node", "-e", harness, str(EXT_DIR / "shared.js")],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        call = result["calls"][0]
        self.assertEqual(call["url"], "http://127.0.0.1:9876/extension/pair")
        self.assertEqual(call["options"]["method"], "POST")
        self.assertEqual(json.loads(call["options"]["body"]), {"replace": True})
        self.assertEqual(call["options"]["headers"]["Authorization"], "Bearer secret")
        self.assertTrue(result["result"]["body"]["paired"])

    def test_token_vault_migrates_legacy_storage_and_restricts_untrusted_access(self):
        background_js = (EXT_DIR / "background.js").read_text(encoding="utf-8")
        vault_js = (EXT_DIR / "credential-vault.js").read_text(encoding="utf-8")

        self.assertIn('importScripts("credential-vault.js")', background_js)
        self.assertIn('setAccessLevel({ accessLevel: "TRUSTED_CONTEXTS" })', background_js)
        self.assertIn('storageGet({ apiToken: "" })', background_js)
        self.assertIn('CredentialVault.setToken(legacyToken)', background_js)
        self.assertIn('storageRemove("apiToken")', background_js)
        self.assertIn('indexedDB.open(DATABASE_NAME, 1)', vault_js)
        self.assertNotIn("console.", background_js + vault_js)

    def test_extension_assets_share_runtime_and_sidepanel_styles(self):
        background_js = (EXT_DIR / "background.js").read_text(encoding="utf-8")
        options_html = (EXT_DIR / "options.html").read_text(encoding="utf-8")
        options_js = (EXT_DIR / "options.js").read_text(encoding="utf-8")
        sidepanel_html = (EXT_DIR / "sidepanel.html").read_text(encoding="utf-8")
        popup_css = (EXT_DIR / "popup.css").read_text(encoding="utf-8")

        self.assertIn('importScripts("i18n.js", "shared.js")', background_js)
        self.assertLess(options_html.index('src="shared.js"'), options_html.index('src="options.js"'))
        self.assertNotIn("<style", sidepanel_html)
        self.assertIn('class="sidepanel-body"', sidepanel_html)
        self.assertIn(".sidepanel-body", popup_css)
        for source in (background_js, options_js):
            self.assertNotIn("const DEFAULTS =", source)
            self.assertNotIn("function storageGet(", source)
            self.assertNotIn("function storageSet(", source)
        self.assertNotIn("async function enqueuePendingSave(", background_js)

    def test_settings_popup_and_sidepanel_round_trip_through_background_vault(self):
        background_js = (EXT_DIR / "background.js").read_text(encoding="utf-8")
        shared_js = (EXT_DIR / "shared.js").read_text(encoding="utf-8")
        options_js = (EXT_DIR / "options.js").read_text(encoding="utf-8")

        self.assertIn('message.type === "bop:get-config"', background_js)
        self.assertIn('message.type === "bop:set-api-token"', background_js)
        self.assertIn("sender.id !== api.runtime.id", background_js)
        self.assertIn('String(sender.url || "").startsWith(trustedRoot)', background_js)
        self.assertIn('apiToken: await CredentialVault.getToken()', background_js)
        self.assertIn('runtimeMessage({ type: "bop:get-config" })', shared_js)
        self.assertIn('runtimeMessage({ type: "bop:get-config" })', options_js)
        self.assertIn('{ ...DEFAULTS, ...response.config }', shared_js)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for the extension service-worker harness")
    def test_background_vault_migration_and_trusted_message_round_trip(self):
        harness = r"""
const fs = require("fs");
const path = require("path");
const vm = require("vm");

const state = { apiPort: 8765, defaultCategory: "Research", apiToken: "legacy-secret" };
let vaultToken = "";
let accessLevel = "";
let messageListener;
const noopEvent = { addListener() {} };

const local = {
  async get(keys) {
    if (Array.isArray(keys)) return Object.fromEntries(keys.map(key => [key, state[key]]));
    if (typeof keys === "string") return { [keys]: state[keys] };
    const result = {};
    for (const [key, fallback] of Object.entries(keys || {})) {
      result[key] = Object.prototype.hasOwnProperty.call(state, key) ? state[key] : fallback;
    }
    return result;
  },
  async set(values) { Object.assign(state, values); },
  async remove(keys) { for (const key of [].concat(keys)) delete state[key]; },
  async setAccessLevel(details) { accessLevel = details.accessLevel; }
};

const chrome = {
  storage: { local },
  runtime: {
    id: "test-extension",
    getURL(path) { return `chrome-extension://test-extension/${path}`; },
    onInstalled: noopEvent,
    onMessage: { addListener(listener) { messageListener = listener; } }
  },
  contextMenus: { create() {}, onClicked: noopEvent },
  sidePanel: { setPanelBehavior: async () => {}, open: async () => {} }
};

const context = vm.createContext({
  chrome,
  fetch: async () => ({ status: 201 }),
  console,
  setTimeout,
  clearTimeout
});
context.globalThis = context;
context.importScripts = (...names) => {
  for (const name of names) {
    if (name === "shared.js" || name === "i18n.js") {
      vm.runInContext(fs.readFileSync(path.join(path.dirname(process.argv[1]), name), "utf8"), context);
      continue;
    }
    if (name === "credential-vault.js") {
      context.CredentialVault = {
        async getToken() { return vaultToken; },
        async setToken(value) {
          const token = typeof value === "string" ? value.trim() : "";
          if (!token) throw new Error("A token is required");
          vaultToken = token;
        }
      };
    }
  }
};

vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);

function send(message, url = "chrome-extension://test-extension/popup.html") {
  return new Promise(resolve => {
    const accepted = messageListener(message, { id: "test-extension", url }, resolve);
    if (!accepted) resolve({ rejected: true });
  });
}

(async () => {
  await new Promise(resolve => setImmediate(resolve));
  const migrated = await send({ type: "bop:get-config" });
  const updated = await send({ type: "bop:set-api-token", apiToken: "replacement-secret" }, "chrome-extension://test-extension/options.html");
  const roundTrip = await send({ type: "bop:get-config" }, "chrome-extension://test-extension/sidepanel.html");
  const untrusted = await send({ type: "bop:get-config" }, "https://example.com/page");
  process.stdout.write(JSON.stringify({ accessLevel, state, vaultToken, migrated, updated, roundTrip, untrusted }));
})().catch(error => { process.stderr.write(error.message); process.exit(1); });
"""
        completed = subprocess.run(
            ["node", "-e", harness, str(EXT_DIR / "background.js")],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["accessLevel"], "TRUSTED_CONTEXTS")
        self.assertNotIn("apiToken", result["state"])
        self.assertEqual(result["migrated"]["config"]["apiToken"], "legacy-secret")
        self.assertTrue(result["updated"]["ok"])
        self.assertEqual(result["vaultToken"], "replacement-secret")
        self.assertEqual(result["roundTrip"]["config"]["apiToken"], "replacement-secret")
        self.assertTrue(result["untrusted"]["rejected"])

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for the shared extension harness")
    def test_shared_pending_queue_normalizes_and_deduplicates(self):
        harness = r"""
const fs = require("fs");
const vm = require("vm");
const state = {};
const local = {
  async get(keys) {
    const result = {};
    for (const [key, fallback] of Object.entries(keys || {})) {
      result[key] = Object.prototype.hasOwnProperty.call(state, key) ? state[key] : fallback;
    }
    return result;
  },
  async set(values) { Object.assign(state, values); }
};
const chrome = { storage: { local }, runtime: { sendMessage: async () => ({}), getURL: path => path } };
const context = vm.createContext({ chrome, console, fetch: async () => ({ status: 201 }), Date, Math });
context.globalThis = context;
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
vm.runInContext(`(async () => {
  await enqueuePendingSave({ url: "https://example.com", title: "First", tags: "one" }, "offline");
  await enqueuePendingSave({ url: "https://example.com", title: "Updated", tags: ["two"] }, "HTTP 503");
  globalThis.result = await getPendingSaves();
})()`, context).then(() => process.stdout.write(JSON.stringify(context.result)));
"""
        completed = subprocess.run(
            ["node", "-e", harness, str(EXT_DIR / "shared.js")],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        pending = json.loads(completed.stdout)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["payload"]["title"], "Updated")
        self.assertEqual(pending[0]["payload"]["tags"], ["two"])
        self.assertEqual(pending[0]["reason"], "HTTP 503")
        self.assertEqual(pending[0]["source"], "context_menu")

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

    def test_optional_browser_snapshot_contract_is_sanitized_and_cookie_free(self):
        shared_js = (EXT_DIR / "shared.js").read_text(encoding="utf-8")
        popup_html = (EXT_DIR / "popup.html").read_text(encoding="utf-8")
        sidepanel_html = (EXT_DIR / "sidepanel.html").read_text(encoding="utf-8")
        popup_js = (EXT_DIR / "popup.js").read_text(encoding="utf-8")
        sidepanel_js = (EXT_DIR / "sidepanel.js").read_text(encoding="utf-8")

        self.assertIn("async function captureSanitizedPage", shared_js)
        self.assertIn("async function capturePageInDocument", shared_js)
        self.assertIn('headers["X-BOP-Capture-Version"] = "1"', shared_js)
        self.assertIn('source_url: location.href', shared_js)
        self.assertIn('selection,', shared_js)
        self.assertIn('document.title.slice(0, 500)', shared_js)
        self.assertIn('element.removeAttribute(attribute.name)', shared_js)
        self.assertIn("per_resource_bytes: 524288", shared_js)
        self.assertIn("total_resource_bytes: 3000000", shared_js)
        self.assertIn('credentials: "include"', shared_js)
        self.assertIn('omit("cross-origin")', shared_js)
        self.assertIn('omit("per-resource-limit")', shared_js)
        self.assertIn('omit("total-resource-limit")', shared_js)
        self.assertNotIn("document.cookie", shared_js)
        self.assertNotIn("localStorage", shared_js)
        self.assertIn('id="captureSnapshot"', popup_html)
        self.assertIn('id="addCaptureSnapshot"', sidepanel_html)
        self.assertIn("payload.browser_snapshot = await captureSanitizedPage(activeTab.id)", popup_js)
        self.assertIn("payload.browser_snapshot = await captureSanitizedPage(tabs[0].id)", sidepanel_js)
        for html in (popup_html, sidepanel_html):
            self.assertIn("cookies are never sent", html)

    @unittest.skipUnless(
        importlib.util.find_spec("playwright"),
        "Playwright is required for the authenticated capture fixture",
    )
    def test_authenticated_fixture_capture_is_bounded_and_offline_renderable(self):
        from playwright.sync_api import sync_playwright

        image = b"\x89PNG\r\n\x1a\n" + (b"i" * 64)
        large_image = b"\x89PNG\r\n\x1a\n" + (b"x" * 524_281)
        aggregate_image = b"\x89PNG\r\n\x1a\n" + (b"a" * 449_992)
        font = b"wOF2" + (b"f" * 64)
        unauthorized_assets = []

        class FixtureHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/":
                    aggregate = "".join(
                        f'<img class="aggregate" src="/aggregate-{index}.png">'
                        for index in range(7)
                    )
                    body = (
                        "<!doctype html><html><head>"
                        '<link rel="stylesheet" href="/style.css">'
                        "<script>document.documentElement.dataset.active='yes'</script>"
                        "</head><body onload=steal()>"
                        '<img id="hero" src="/hero.png">'
                        '<img id="large" src="/large.png">'
                        '<img id="foreign" src="http://localhost:9/private.png">'
                        f"{aggregate}<form><input value=secret></form><p>Private fixture</p>"
                        "</body></html>"
                    ).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.send_header("Set-Cookie", "fixture_session=allowed; SameSite=Strict")
                else:
                    if "fixture_session=allowed" not in self.headers.get("Cookie", ""):
                        unauthorized_assets.append(self.path)
                        self.send_error(401)
                        return
                    if self.path == "/style.css":
                        body = (
                            "@font-face{font-family:fixture;src:url('/font.woff2')}"
                            "body{font-family:fixture;background-image:url('/background.png')}"
                        ).encode()
                        content_type = "text/css"
                    elif self.path in {"/hero.png", "/background.png"}:
                        body, content_type = image, "image/png"
                    elif self.path == "/large.png":
                        body, content_type = large_image, "image/png"
                    elif self.path.startswith("/aggregate-"):
                        body, content_type = aggregate_image, "image/png"
                    elif self.path == "/font.woff2":
                        body, content_type = font, "font/woff2"
                    else:
                        self.send_error(404)
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args):
                pass

        fixture = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        fixture_thread = threading.Thread(target=fixture.serve_forever, daemon=True)
        fixture_thread.start()
        fixture_url = f"http://127.0.0.1:{fixture.server_port}/"
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(fixture_url, wait_until="networkidle")
                page.evaluate("window.chrome = {}")
                page.add_script_tag(path=str(EXT_DIR / "shared.js"))
                disabled_capture = page.evaluate(
                    "capturePageInDocument({inlineResources: false})"
                )
                capture = page.evaluate("capturePageInDocument({inlineResources: true})")
                browser.close()
        finally:
            fixture.shutdown()
            fixture.server_close()
            fixture_thread.join(timeout=2)

        self.assertNotIn("error", capture)
        self.assertFalse(unauthorized_assets)
        self.assertEqual(disabled_capture["resources"]["inlined"], 0)
        self.assertGreater(
            disabled_capture["resources"]["omitted_by_reason"]["inlining-disabled"],
            0,
        )
        self.assertGreaterEqual(capture["resources"]["inlined"], 3)
        reasons = capture["resources"]["omitted_by_reason"]
        self.assertGreaterEqual(reasons["cross-origin"], 1)
        self.assertGreaterEqual(reasons["per-resource-limit"], 1)
        self.assertGreaterEqual(reasons["total-resource-limit"], 1)
        self.assertLessEqual(capture["resources"]["inlined_bytes"], 3_000_000)
        self.assertNotIn("<script", capture["html"].lower())
        self.assertNotIn("<form", capture["html"].lower())
        self.assertNotIn("onload=", capture["html"].lower())
        self.assertIn("data:image/png;base64,", capture["html"])
        self.assertIn("data:font/woff2;base64,", capture["html"])
        self.assertNotIn("/hero.png", capture["html"])
        self.assertNotIn("/style.css", capture["html"])
        self.assertNotRegex(capture["html"], r'(?:src|href)=["\']https?://')
        self.assertNotRegex(capture["html"], r'url\(["\']?https?://')

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
        payload = extract_js_object_literal(background_js, "const payload =")

        self.assertIn("url,", payload)
        self.assertIn("title: title || url", payload)
        self.assertIn("category: values.defaultCategory", payload)
        self.assertIn("tags: []", payload)
        self.assertIn('notes: notes || ""', payload)

    def test_extension_pending_save_queue_contract(self):
        shared_js = (EXT_DIR / "shared.js").read_text(encoding="utf-8")
        background_js = (EXT_DIR / "background.js").read_text(encoding="utf-8")
        popup_html = (EXT_DIR / "popup.html").read_text(encoding="utf-8")
        sidepanel_html = (EXT_DIR / "sidepanel.html").read_text(encoding="utf-8")
        popup_js = (EXT_DIR / "popup.js").read_text(encoding="utf-8")
        sidepanel_js = (EXT_DIR / "sidepanel.js").read_text(encoding="utf-8")

        self.assertIn('PENDING_SAVES_KEY = "pendingSaves"', shared_js)
        self.assertIn("enqueuePendingSave", background_js)
        self.assertIn("HTTP ${response.status}", background_js)
        self.assertIn("API unavailable", background_js)
        self.assertIn("result.status === 201 || result.status === 409", shared_js)
        for html in (popup_html, sidepanel_html):
            self.assertIn('id="pendingPanel"', html)
            self.assertIn('id="pendingCount"', html)
            self.assertIn('id="retryPending"', html)
            self.assertIn('id="clearPending"', html)
        for js in (popup_js, sidepanel_js):
            self.assertIn("refreshPendingPanel", js)
            self.assertIn("retryPendingSaves", js)
            self.assertIn("clearPendingSaves", js)

    def test_extension_assets_exist(self):
        for name in [
            "manifest.json",
            "popup.html",
            "popup.js",
            "popup.css",
            "i18n.js",
            "options.html",
            "options.js",
            "shared.js",
            "credential-vault.js",
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

    def _post_json(
        self,
        base_url: str,
        payload,
        token: str = "",
        extra_headers=None,
        path: str = "/bookmarks",
    ):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        headers.update(extra_headers or {})
        request = urllib.request.Request(
            f"{base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def _pair_extension(self, base_url: str, token: str, origin: str, *, replace: bool = False):
        return self._post_json(
            base_url,
            {"replace": replace},
            token,
            {"Origin": origin},
            path="/extension/pair",
        )

    def _get_json(self, base_url: str, path: str, token: str = ""):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        request = urllib.request.Request(f"{base_url}{path}", headers=headers)
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_bounded_server_keeps_health_and_save_responsive_during_snapshot(self):
        import main
        from bookmark_organizer_pro.services.snapshot import SnapshotArchiver

        origin = f"chrome-extension://{'c' * 32}"
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            api = main.BookmarkAPI(
                manager,
                port=0,
                extension_origins_file=Path(tmp) / "approved-origins.json",
                max_workers=4,
            )
            slow_client = socket.socket()
            release_snapshot = threading.Event()
            snapshot_entered = threading.Event()
            original_import = SnapshotArchiver.import_browser_snapshot

            def delayed_import(archiver, *args, **kwargs):
                snapshot_entered.set()
                if not release_snapshot.wait(2):
                    raise RuntimeError("test snapshot release timed out")
                return original_import(archiver, *args, **kwargs)

            try:
                api.start()
                token = self._api_token()
                base_url = f"http://127.0.0.1:{api.port}"
                status, body = self._pair_extension(base_url, token, origin)
                self.assertEqual(status, 200, body)

                slow_client.connect(("127.0.0.1", api.port))
                slow_client.sendall(b"GET /health HTTP/1.1\r\nHost: 127.0.0.1")
                capture = {
                    "url": "https://example.com/concurrent-capture",
                    "title": "Concurrent capture",
                    "browser_snapshot": {
                        "html": "<html><body>captured</body></html>",
                        "source_url": "https://example.com/concurrent-capture",
                    },
                }
                headers = {"Origin": origin, "X-BOP-Capture-Version": "1"}
                with mock.patch.object(SnapshotArchiver, "import_browser_snapshot", delayed_import):
                    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                        snapshot_future = executor.submit(
                            self._post_json, base_url, capture, token, headers,
                        )
                        self.assertTrue(snapshot_entered.wait(1))
                        health_future = executor.submit(self._get_json, base_url, "/health")
                        save_future = executor.submit(
                            self._post_json,
                            base_url,
                            {"url": "https://example.com/concurrent-save"},
                            token,
                        )
                        self.assertEqual(health_future.result(timeout=1)[1]["status"], "ok")
                        self.assertEqual(save_future.result(timeout=1)[0], 201)
                        release_snapshot.set()
                        snapshot_status, snapshot_body = snapshot_future.result(timeout=2)
                self.assertEqual(snapshot_status, 201, snapshot_body)
                self.assertTrue(snapshot_body["browser_snapshot"]["stored"])
                self.assertEqual(len(manager.get_all_bookmarks()), 2)
            finally:
                release_snapshot.set()
                slow_client.close()
                api.stop()

    def test_slow_headers_and_bodies_expire_and_release_the_worker(self):
        import main

        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            api = main.BookmarkAPI(
                manager,
                port=0,
                max_workers=1,
                header_deadline_seconds=0.2,
                request_deadline_seconds=0.2,
                io_timeout_seconds=0.2,
            )
            header_client = socket.socket()
            body_client = socket.socket()
            try:
                api.start()
                token = self._api_token()
                base_url = f"http://127.0.0.1:{api.port}"

                header_client.connect(("127.0.0.1", api.port))
                header_client.sendall(b"GET /health HTTP/1.1\r\nHost: 127.0.0.1")
                saturation_deadline = time.monotonic() + 1
                while (
                    time.monotonic() < saturation_deadline
                    and not api._server.at_capacity
                ):
                    time.sleep(0.005)
                self.assertTrue(api._server.at_capacity)
                with self.assertRaises(urllib.error.HTTPError) as busy:
                    self._get_json(base_url, "/health")
                self.assertEqual(busy.exception.code, 503)
                time.sleep(0.3)
                self.assertEqual(self._get_json(base_url, "/health")[0], 200)

                body_client.connect(("127.0.0.1", api.port))
                request_headers = (
                    "POST /bookmarks HTTP/1.1\r\n"
                    "Host: 127.0.0.1\r\n"
                    f"Authorization: Bearer {token}\r\n"
                    "Content-Type: application/json\r\n"
                    "Content-Length: 100\r\n\r\n"
                ).encode("ascii")
                body_client.sendall(request_headers + b"{")
                time.sleep(0.3)
                self.assertEqual(self._get_json(base_url, "/health")[1]["status"], "ok")
                self.assertEqual(manager.get_all_bookmarks(), [])
            finally:
                header_client.close()
                body_client.close()
                api.stop()

    def test_handler_deadline_disconnects_a_stalled_request_without_blocking_health(self):
        import main

        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            api = main.BookmarkAPI(
                manager,
                port=0,
                max_workers=2,
                request_deadline_seconds=0.2,
                io_timeout_seconds=0.2,
            )
            release_handler = threading.Event()
            handler_entered = threading.Event()
            original_stats = manager.get_statistics

            def delayed_stats():
                handler_entered.set()
                release_handler.wait(2)
                return original_stats()

            try:
                api.start()
                token = self._api_token()
                base_url = f"http://127.0.0.1:{api.port}"
                with mock.patch.object(manager, "get_statistics", delayed_stats):
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        stalled = executor.submit(self._get_json, base_url, "/stats", token)
                        self.assertTrue(handler_entered.wait(1))
                        self.assertEqual(self._get_json(base_url, "/health")[1]["status"], "ok")
                        with self.assertRaises((OSError, urllib.error.URLError)):
                            stalled.result(timeout=1)
                        release_handler.set()
            finally:
                release_handler.set()
                api.stop()

    def test_extension_origin_pairing_rejects_unpaired_and_supports_explicit_rotation(self):
        import main

        first_origin = f"chrome-extension://{'a' * 32}"
        second_origin = f"chrome-extension://{'b' * 32}"
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            api = main.BookmarkAPI(
                manager,
                port=0,
                extension_origins_file=Path(tmp) / "approved-origins.json",
            )
            try:
                api.start()
                token = self._api_token()
                base_url = f"http://127.0.0.1:{api.port}"

                preflight = urllib.request.Request(
                    f"{base_url}/bookmarks",
                    headers={"Origin": first_origin, "Access-Control-Request-Method": "POST"},
                    method="OPTIONS",
                )
                with self.assertRaises(urllib.error.HTTPError) as rejected_preflight:
                    urllib.request.urlopen(preflight, timeout=3)
                self.assertEqual(rejected_preflight.exception.code, 403)
                self.assertEqual(rejected_preflight.exception.headers["Access-Control-Allow-Origin"], "null")

                status, body = self._post_json(
                    base_url,
                    {"url": "https://example.com/unpaired"},
                    token,
                    {"Origin": first_origin},
                )
                self.assertEqual(status, 403)
                self.assertIn("not paired", body["error"])

                status, body = self._pair_extension(base_url, token, first_origin)
                self.assertEqual(status, 200, body)
                self.assertTrue(body["paired"])
                self.assertTrue(body["changed"])

                with urllib.request.urlopen(preflight, timeout=3) as allowed_preflight:
                    self.assertEqual(allowed_preflight.status, 204)
                    self.assertEqual(allowed_preflight.headers["Access-Control-Allow-Origin"], first_origin)

                status, body = self._post_json(
                    base_url,
                    {"url": "https://example.com/paired"},
                    token,
                    {"Origin": first_origin},
                )
                self.assertEqual(status, 201, body)

                status, body = self._pair_extension(base_url, token, second_origin)
                self.assertEqual(status, 409)
                self.assertTrue(body["replace_required"])

                status, body = self._pair_extension(base_url, token, second_origin, replace=True)
                self.assertEqual(status, 200, body)
                self.assertTrue(body["paired"])

                status, _ = self._post_json(
                    base_url,
                    {"url": "https://example.com/old-extension"},
                    token,
                    {"Origin": first_origin},
                )
                self.assertEqual(status, 403)

                status, body = self._post_json(
                    base_url,
                    {"url": "https://example.com/non-browser-client"},
                    token,
                )
                self.assertEqual(status, 201, body)

                persisted = json.loads((Path(tmp) / "approved-origins.json").read_text(encoding="utf-8"))
                self.assertEqual(persisted["origins"], [second_origin])
            finally:
                api.stop()

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

    def test_authenticated_browser_snapshot_is_sanitized_and_stored(self):
        import main

        malicious_html = """<!doctype html><html><head>
        <script>document.cookie='stolen=1'</script>
        <style>@import url(https://tracker.example/a.css);
        @font-face{font-family:safe;src:url(data:font/woff2;base64,d09GMg==)}
        body{color:red;background:url(data:image/png;base64,iVBORw0KGgo=)}
        .unsafe{background:url(data:image/svg+xml;base64,PHN2Zz4=)}</style>
        </head><body onload="steal()">
        <iframe src="https://private.example/account"></iframe>
        <img src="https://private.example/avatar" onerror="steal()">
        <img id="embedded" src="data:image/png;base64,iVBORw0KGgo=">
        <img id="unsafe" src="data:image/svg+xml;base64,PHN2Zz4=">
        <a href="javascript:steal()">bad</a><a href="https://example.com/next">next</a>
        <form action="https://evil.example"><input value="secret"></form>
        <p>Authenticated account content</p></body></html>"""
        url = "https://example.com/account?session-page=1"
        payload = {
            "url": url,
            "title": "Account",
            "browser_snapshot": {
                "html": malicious_html,
                "source_url": url,
                "title": "Account",
                "selection": "private selection",
                "resources": {
                    "count": 9,
                    "inlined": 3,
                    "inlined_bytes": 128,
                    "omitted": 6,
                    "omitted_by_reason": {"cross-origin": 4, "per-resource-limit": 2},
                },
            },
        }
        capture_headers = {
            "Origin": f"chrome-extension://{'a' * 32}",
            "X-BOP-Capture-Version": "1",
        }

        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            api = main.BookmarkAPI(
                manager,
                port=0,
                extension_origins_file=Path(tmp) / "approved-origins.json",
            )
            try:
                api.start()
                token = self._api_token()
                status, body = self._pair_extension(
                    f"http://127.0.0.1:{api.port}", token, capture_headers["Origin"],
                )
                self.assertEqual(status, 200, body)
                status, body = self._post_json(
                    f"http://127.0.0.1:{api.port}", payload, token, capture_headers,
                )
                self.assertEqual(status, 201, body)
                self.assertTrue(body["browser_snapshot"]["stored"])
                self.assertEqual(body["browser_snapshot"]["resource_count"], 9)
                self.assertEqual(body["browser_snapshot"]["resources"]["inlined"], 3)
                self.assertEqual(
                    body["browser_snapshot"]["resources"]["omitted_by_reason"],
                    {"cross-origin": 4, "per-resource-limit": 2},
                )
                snapshot_path = Path(body["snapshot_path"])
                self.assertTrue(snapshot_path.is_file())
                self.assertEqual(snapshot_path.parent, Path(tmp) / "snapshots")
                stored = snapshot_path.read_text(encoding="utf-8")
                self.assertIn("Authenticated account content", stored)
                self.assertIn("cookies were never transferred", stored)
                self.assertIn("Content-Security-Policy", stored)
                self.assertNotIn("<script", stored.lower())
                self.assertNotIn("<iframe", stored.lower())
                self.assertNotIn("onload=", stored.lower())
                self.assertNotIn("javascript:", stored.lower())
                self.assertNotIn("https://private.example/avatar", stored)
                self.assertNotIn("tracker.example", stored)
                self.assertIn("data:image/png;base64,iVBORw0KGgo=", stored)
                self.assertIn("data:font/woff2;base64,d09GMg==", stored)
                self.assertNotIn("data:image/svg+xml", stored)
                self.assertFalse(list(snapshot_path.parent.glob(".*.tmp")))
            finally:
                api.stop()

    def test_browser_snapshot_rejects_untrusted_origin_and_source_mismatch(self):
        import main

        payload = {
            "url": "https://example.com/account",
            "browser_snapshot": {
                "html": "<html><body>account</body></html>",
                "source_url": "https://example.com/account",
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            manager = self._make_manager(tmp)
            api = main.BookmarkAPI(
                manager,
                port=0,
                extension_origins_file=Path(tmp) / "approved-origins.json",
            )
            try:
                api.start()
                token = self._api_token()
                base_url = f"http://127.0.0.1:{api.port}"
                status, body = self._post_json(
                    base_url, payload, token, {"X-BOP-Capture-Version": "1"},
                )
                self.assertEqual(status, 403)
                self.assertIn("Origin", body["error"])

                paired_origin = f"chrome-extension://{'b' * 32}"
                status, body = self._pair_extension(base_url, token, paired_origin)
                self.assertEqual(status, 200, body)

                payload["browser_snapshot"]["source_url"] = "https://evil.example/account"
                status, body = self._post_json(
                    base_url,
                    payload,
                    token,
                    {"Origin": paired_origin, "X-BOP-Capture-Version": "1"},
                )
                self.assertEqual(status, 400)
                self.assertIn("source URL", body["error"])
                self.assertEqual(manager.get_all_bookmarks(), [])

                payload["browser_snapshot"]["source_url"] = payload["url"]
                payload["browser_snapshot"]["html"] = "x" * 5_000_001
                status, body = self._post_json(
                    base_url,
                    payload,
                    token,
                    {"Origin": paired_origin, "X-BOP-Capture-Version": "1"},
                )
                self.assertEqual(status, 422)
                self.assertIn("5 MB", body["error"])
                self.assertEqual(manager.get_all_bookmarks(), [])
            finally:
                api.stop()


if __name__ == "__main__":
    unittest.main()
