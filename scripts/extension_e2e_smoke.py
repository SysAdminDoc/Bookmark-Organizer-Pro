#!/usr/bin/env python3
"""Exercise the real unpacked Manifest V3 extension in headless Chromium."""

from __future__ import annotations

import argparse
import json
import tempfile
import threading
import time
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
EXTENSION_DIR = ROOT / "browser-extension"
TOKEN = "extension-e2e-local-token"


class ExtensionSmokeError(RuntimeError):
    """Raised when an extension contract fails in the loaded browser."""


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str = ""


def validate_report(checks: Sequence[CheckResult]) -> None:
    """Fail a smoke report with a compact list of broken contracts."""
    failures = [check for check in checks if check.status == "failed"]
    if failures:
        detail = "; ".join(
            f"{check.name}: {check.detail or 'failed'}" for check in failures
        )
        raise ExtensionSmokeError(detail)


class _FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b"""<!doctype html><html><head><title>Extension E2E Fixture</title>
<script>window.fixtureSecret = 'remove-me'</script></head><body>
<main><h1>Loaded extension capture</h1><p id="selection">Persistent Chromium proof.</p>
<form><input value="private"></form></main></body></html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *_args: Any) -> None:
        return


def _start_fixture_server() -> tuple[ThreadingHTTPServer, threading.Thread]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _make_manager(data_dir: Path):
    from bookmark_organizer_pro.core import CategoryManager
    from bookmark_organizer_pro.managers import BookmarkManager, TagManager

    return BookmarkManager(
        CategoryManager(filepath=data_dir / "categories.json"),
        TagManager(filepath=data_dir / "tags.json"),
        filepath=data_dir / "bookmarks.json",
    )


def _wait_for_service_worker(context, *, timeout: int = 15_000):
    workers = context.service_workers
    if workers:
        return workers[0]
    return context.wait_for_event("serviceworker", timeout=timeout)


def _worker_check(worker, expression: str, name: str) -> CheckResult:
    try:
        result = worker.evaluate(expression)
    except Exception as exc:
        return CheckResult(name, "failed", str(exc))
    if isinstance(result, dict) and not result.get("ok", True):
        return CheckResult(name, "failed", str(result.get("error") or result))
    return CheckResult(name, "passed", json.dumps(result, sort_keys=True, default=str))


def _wait_for_text(locator, expected: str, *, timeout: float = 10.0) -> str:
    """Poll extension DOM text without CSP-blocked JavaScript evaluation."""
    deadline = time.monotonic() + timeout
    last = ""
    while time.monotonic() < deadline:
        last = locator.inner_text()
        if expected in last:
            return last
        time.sleep(0.05)
    raise ExtensionSmokeError(f"Timed out waiting for {expected!r}; last text was {last!r}")


def _restart_extension(context, worker):
    worker_url = worker.url
    extension_root = "/".join(worker_url.split("/")[:3])
    try:
        browser = context.browser
        if browser is None:
            raise RuntimeError("persistent context has no Chromium browser handle")
        cdp = browser.new_browser_cdp_session()
        targets = cdp.send("Target.getTargets").get("targetInfos", [])
        target = next(
            (
                item
                for item in targets
                if item.get("type") == "service_worker" and item.get("url") == worker_url
            ),
            None,
        )
        if target is None:
            raise RuntimeError("loaded extension service-worker target was not found")
        old_target_id = target["targetId"]
        closed = cdp.send("Target.closeTarget", {"targetId": old_target_id})
        if not closed.get("success"):
            raise RuntimeError("Chromium refused to stop the extension service worker")
        stopped = False
        destroy_deadline = time.monotonic() + 5
        while time.monotonic() < destroy_deadline:
            try:
                worker.evaluate("chrome.runtime.id")
            except Exception:
                stopped = True
                break
            time.sleep(0.05)
        if not stopped:
            raise RuntimeError("the original service-worker execution target stayed alive")
        wake_page = context.new_page()
        try:
            wake_page.goto(
                f"{extension_root}/options.html",
                wait_until="domcontentloaded",
            )
            wake_page.evaluate("loadOptions()")
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                targets = cdp.send("Target.getTargets").get("targetInfos", [])
                replacement = next(
                    (
                        item
                        for item in targets
                        if item.get("type") == "service_worker"
                        and item.get("url") == worker_url
                    ),
                    None,
                )
                if replacement is not None:
                    cdp.detach()
                    return wake_page
                time.sleep(0.05)
            remaining = [
                (item.get("targetId"), item.get("url"))
                for item in cdp.send("Target.getTargets").get("targetInfos", [])
                if item.get("type") == "service_worker"
            ]
            raise TimeoutError(
                f"replacement service-worker target was not observable; targets={remaining}"
            )
        except Exception:
            wake_page.close()
            cdp.detach()
            raise
    except Exception as exc:
        raise ExtensionSmokeError(f"service worker did not restart: {exc}") from exc


def run_smoke(
    *, profile_dir: Path, data_dir: Path, extension_dir: Path = EXTENSION_DIR
) -> dict[str, Any]:
    """Run the loaded-extension smoke and return a machine-readable report."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - environment-specific
        raise ExtensionSmokeError("Playwright is not installed") from exc

    from bookmark_organizer_pro.services import api as api_module

    manager = _make_manager(data_dir)
    original_token_loader = api_module._load_or_create_token
    api_module._load_or_create_token = lambda: TOKEN
    api = api_module.BookmarkAPI(
        manager,
        port=0,
        extension_origins_file=data_dir / "approved_extension_origins.json",
    )
    fixture, fixture_thread = _start_fixture_server()
    checks: list[CheckResult] = []
    console_errors: list[str] = []
    context = None
    try:
        api.start()
        fixture_url = f"http://127.0.0.1:{fixture.server_port}/fixture"
        extension_path = str(extension_dir.resolve())
        if not (extension_dir / "manifest.json").is_file():
            raise ExtensionSmokeError(f"Chromium extension manifest not found: {extension_dir}")
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(profile_dir),
                channel="chromium",
                headless=True,
                args=[
                    f"--disable-extensions-except={extension_path}",
                    f"--load-extension={extension_path}",
                ],
            )
            worker = _wait_for_service_worker(context)
            worker.on(
                "console",
                lambda message: console_errors.append(message.text)
                if message.type == "error"
                else None,
            )
            extension_id = worker.url.split("/")[2]
            extension_root = f"chrome-extension://{extension_id}"

            checks.append(
                _worker_check(
                    worker,
                    """async () => {
                      const required = ['activeTab','scripting','storage','contextMenus','sidePanel','readingList'];
                      const granted = await chrome.permissions.getAll();
                      const missing = required.filter(value => !(granted.permissions || []).includes(value));
                      return {ok: missing.length === 0, missing, granted: granted.permissions || []};
                    }""",
                    "permissions",
                )
            )
            checks.append(
                _worker_check(
                    worker,
                    """async () => new Promise(resolve => {
                      chrome.contextMenus.update('save-to-bop', {visible: true}, () => {
                        const error = chrome.runtime.lastError && chrome.runtime.lastError.message;
                        resolve({ok: !error, error: error || ''});
                      });
                    })""",
                    "context_menu_registration",
                )
            )
            checks.append(
                _worker_check(
                    worker,
                    """async () => {
                      if (!chrome.sidePanel || !chrome.sidePanel.getOptions) {
                        return {ok: false, error: 'Side Panel API unavailable'};
                      }
                      const options = await chrome.sidePanel.getOptions({});
                      return {ok: options.path === 'sidepanel.html', options};
                    }""",
                    "side_panel",
                )
            )

            options = context.new_page()
            options.on(
                "console",
                lambda message: console_errors.append(f"options: {message.text}")
                if message.type == "error"
                else None,
            )
            options.on("pageerror", lambda error: console_errors.append(f"options: {error}"))
            options.goto(f"{extension_root}/options.html", wait_until="domcontentloaded")
            options.evaluate("loadOptions()")
            options.fill("#apiPort", str(api.port))
            options.fill("#apiToken", TOKEN)
            options.fill("#defaultCategory", "Research")
            options.click("#saveOptions")
            options.locator("#status").wait_for(state="visible")
            try:
                _wait_for_text(options.locator("#status"), "paired")
            except ExtensionSmokeError as exc:
                diagnostic = options.evaluate(
                    """async ({port, token}) => {
                      let runtime;
                      try { runtime = await runtimeMessage({type: 'bop:get-config'}); }
                      catch (error) { runtime = {error: String(error)}; }
                      let pairing;
                      try {
                        const response = await fetch(`http://127.0.0.1:${port}/extension/pair`, {
                          method: 'POST', headers: {'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json'},
                          body: JSON.stringify({replace: false})
                        });
                        pairing = {status: response.status, body: await response.text()};
                      } catch (error) { pairing = {error: String(error)}; }
                      return {runtime, pairing};
                    }""",
                    {"port": api.port, "token": TOKEN},
                )
                raise ExtensionSmokeError(
                    f"{exc}; diagnostic={diagnostic}; console={console_errors}"
                ) from exc
            checks.append(CheckResult("live_api_pairing", "passed", options.locator("#status").inner_text()))

            config_before = options.evaluate("getConfig()")
            if config_before.get("apiToken") != TOKEN:
                checks.append(CheckResult("credential_storage", "failed", "token did not round trip"))
            else:
                checks.append(CheckResult("credential_storage", "passed", "IndexedDB vault round trip"))
            options.close()

            context_result = worker.evaluate(
                """async ({url}) => ({
                  saved: await quickSave(url, 'Context Menu E2E', 'Selected: worker restart proof')
                })""",
                {"url": "https://example.com/extension-e2e-context"},
            )
            if context_result.get("saved") and manager.url_exists("https://example.com/extension-e2e-context"):
                checks.append(CheckResult("context_menu_save", "passed", "quick-save handler reached authenticated API"))
            else:
                checks.append(CheckResult("context_menu_save", "failed", str(context_result)))

            fixture_page = context.new_page()
            fixture_page.goto(fixture_url, wait_until="domcontentloaded")
            fixture_page.bring_to_front()
            capture_result = worker.evaluate(
                """async () => {
                  const tabs = await chrome.tabs.query({active: true, currentWindow: true});
                  const tab = tabs[0];
                  const config = await getTrustedConfig();
                  const snapshot = await captureSanitizedPage(tab.id);
                  return saveBookmarkPayload({
                    url: tab.url, title: tab.title, category: 'Research', browser_snapshot: snapshot
                  }, config);
                }"""
            )
            if capture_result.get("status") == 201 and capture_result.get("body", {}).get("browser_snapshot", {}).get("stored"):
                snapshot_path = Path(capture_result["body"]["snapshot_path"])
                stored = snapshot_path.read_text(encoding="utf-8")
                capture_ok = "Loaded extension capture" in stored and "<script" not in stored.lower()
                checks.append(CheckResult("sanitized_capture", "passed" if capture_ok else "failed", str(snapshot_path)))
            else:
                checks.append(CheckResult("sanitized_capture", "failed", str(capture_result)))

            offline_urls = {
                "popup": "https://example.com/extension-e2e-offline-popup",
                "side_panel": "https://example.com/extension-e2e-offline-side-panel",
                "context_menu": "https://example.com/extension-e2e-offline-context",
                "selection": "https://example.com/extension-e2e-offline-selection",
            }
            queued_results = worker.evaluate(
                """async ({urls}) => {
                  await chrome.storage.local.set({apiPort: 1});
                  const config = await getTrustedConfig();
                  return {
                    popup: await saveBookmarkPayload(
                      {url: urls.popup, title: 'Offline Popup E2E', category: 'Research'},
                      config,
                      {source: 'popup'}
                    ),
                    side_panel: await saveBookmarkPayload(
                      {url: urls.side_panel, title: 'Offline Side Panel E2E', category: 'Research'},
                      config,
                      {source: 'side_panel'}
                    ),
                    context_menu: await quickSave(
                      urls.context_menu, 'Offline Context Menu E2E', '', 'context_menu'
                    ),
                    selection: await quickSave(
                      urls.selection, 'Offline Selection E2E', 'Selected text', 'selection'
                    )
                  };
                }""",
                {"urls": offline_urls},
            )
            pending = worker.evaluate("getPendingSaves()")
            worker.evaluate("port => chrome.storage.local.set({apiPort: port})", api.port)
            retry_page = context.new_page()
            retry_page.goto(f"{extension_root}/sidepanel.html", wait_until="domcontentloaded")
            retry = retry_page.evaluate("retryPendingSaves()")
            second_retry = retry_page.evaluate("retryPendingSaves()")
            retry_page.close()
            saved_urls = [bookmark.url for bookmark in manager.get_all_bookmarks()]
            offline_ok = (
                len(pending) == len(offline_urls)
                and {item.get("source") for item in pending} == set(offline_urls)
                and queued_results["popup"].get("queued")
                and queued_results["side_panel"].get("queued")
                and queued_results["context_menu"] is False
                and queued_results["selection"] is False
                and retry.get("remaining") == 0
                and retry.get("resolved") == len(offline_urls)
                and second_retry.get("attempted") == 0
                and all(saved_urls.count(url) == 1 for url in offline_urls.values())
            )
            offline_detail = {
                "pending_sources": sorted(item.get("source", "") for item in pending),
                "retry": retry,
                "second_retry": second_retry,
            }
            checks.append(
                CheckResult(
                    "offline_queue_exactly_once",
                    "passed" if offline_ok else "failed",
                    json.dumps(offline_detail, sort_keys=True),
                )
            )

            reading_support = worker.evaluate(
                "typeof chrome.readingList !== 'undefined' && typeof chrome.readingList.addEntry === 'function'"
            )
            if reading_support:
                reading_url = "https://example.com/extension-e2e-reading-list"
                worker.evaluate(
                    "entry => chrome.readingList.addEntry(entry)",
                    {"url": reading_url, "title": "Reading List E2E", "hasBeenRead": False},
                )
                panel = context.new_page()
                panel.goto(f"{extension_root}/sidepanel.html", wait_until="domcontentloaded")
                panel.click('[data-tab="add"]')
                panel.click("#importReadingListBtn")
                _wait_for_text(panel.locator("#addStatus"), "Imported")
                reading_ok = manager.url_exists(reading_url)
                checks.append(
                    CheckResult(
                        "reading_list",
                        "passed" if reading_ok else "failed",
                        panel.locator("#addStatus").inner_text(),
                    )
                )
                panel.close()
                worker.evaluate("url => chrome.readingList.removeEntry({url})", reading_url)
            else:
                checks.append(CheckResult("reading_list", "skipped", "Chromium Reading List API unavailable"))

            fixture_page.close()
            restarted = _restart_extension(context, worker)
            restarted.locator("#apiToken").wait_for(state="visible")
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and not restarted.input_value("#apiToken"):
                time.sleep(0.05)
            config_after = restarted.evaluate("getConfig()")
            if config_after.get("apiToken") == TOKEN and config_after.get("apiPort") == api.port:
                checks.append(CheckResult("service_worker_restart", "passed", "credential and config survived"))
            else:
                checks.append(CheckResult("service_worker_restart", "failed", str(config_after)))
            restarted.close()

            if console_errors:
                checks.append(CheckResult("console_errors", "failed", " | ".join(console_errors)))
            else:
                checks.append(CheckResult("console_errors", "passed", "none"))
            validate_report(checks)
            return {
                "extension_id": extension_id,
                "api_port": api.port,
                "bookmark_count": len(manager.get_all_bookmarks()),
                "checks": [asdict(check) for check in checks],
            }
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        fixture.shutdown()
        fixture.server_close()
        fixture_thread.join(timeout=2)
        api.stop()
        api_module._load_or_create_token = original_token_loader


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, help="Persistent Chromium profile directory")
    parser.add_argument("--data-dir", type=Path, help="Temporary BOP data directory")
    parser.add_argument(
        "--extension-dir", type=Path, default=EXTENSION_DIR,
        help="Built Chromium extension directory",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    profile_temp = None
    data_temp = None
    try:
        if args.profile:
            profile = args.profile.resolve()
            profile.mkdir(parents=True, exist_ok=True)
        else:
            profile_temp = tempfile.TemporaryDirectory(prefix="bop-extension-profile-")
            profile = Path(profile_temp.name)
        if args.data_dir:
            data_dir = args.data_dir.resolve()
            data_dir.mkdir(parents=True, exist_ok=True)
        else:
            data_temp = tempfile.TemporaryDirectory(prefix="bop-extension-data-")
            data_dir = Path(data_temp.name)
        report = run_smoke(
            profile_dir=profile,
            data_dir=data_dir,
            extension_dir=args.extension_dir.resolve(),
        )
        print(json.dumps(report, indent=2))
        return 0
    except ExtensionSmokeError as exc:
        print(f"extension e2e smoke failed: {exc}")
        return 1
    finally:
        if profile_temp is not None:
            profile_temp.cleanup()
        if data_temp is not None:
            data_temp.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
