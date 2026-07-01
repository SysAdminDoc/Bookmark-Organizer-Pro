"""Local visual smoke checks for desktop and extension surfaces.

The script captures screenshots into a temporary output directory by default.
It intentionally avoids the user's live bookmark library by running the desktop
app against a temporary BOOKMARK_DATA_DIR unless --data-dir is supplied.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_OUTPUT_DIR = Path(tempfile.gettempdir()) / "bookmark-organizer-pro-visual-smoke"


@dataclass(frozen=True)
class ExtensionSurface:
    name: str
    html_file: str
    viewport: tuple[int, int]
    color_scheme: str
    expected_text: tuple[str, ...]
    click_selector: str = ""


DESKTOP_SURFACES = (
    "desktop-main-empty-dark",
    "desktop-main-list-light",
    "desktop-assistant-settings",
    "desktop-import-progress",
    "desktop-cleanup-review",
    "desktop-read-later-queue",
    "desktop-snapshot-failures-sidebar",
    "desktop-export-dialog",
    "desktop-reader-view",
    "desktop-graph-view",
)

EXTENSION_SURFACES = (
    ExtensionSurface(
        "extension-popup-dark",
        "popup.html",
        (380, 620),
        "dark",
        ("Save Bookmark", "Category", "Read Later"),
    ),
    ExtensionSurface(
        "extension-popup-light",
        "popup.html",
        (380, 620),
        "light",
        ("Save Bookmark", "Options", "Read Later"),
    ),
    ExtensionSurface(
        "extension-options-light",
        "options.html",
        (560, 620),
        "light",
        ("Local API", "Save Settings", "Test API"),
    ),
    ExtensionSurface(
        "extension-sidepanel-recent-dark",
        "sidepanel.html",
        (430, 760),
        "dark",
        ("Recent", "Search", "Connected", "Visual QA Handbook"),
    ),
    ExtensionSurface(
        "extension-sidepanel-add-light",
        "sidepanel.html",
        (430, 760),
        "light",
        ("Add", "Read Later", "Save Bookmark"),
        click_selector='button[data-tab="add"]',
    ),
)


@dataclass(frozen=True)
class CaptureResult:
    name: str
    path: Path
    width: int
    height: int


class VisualSmokeError(AssertionError):
    """Raised when a visual smoke surface fails its contract."""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture and validate local visual smoke screenshots.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR, help="directory for captured PNG files")
    parser.add_argument("--data-dir", type=Path, default=None, help="desktop app data dir; defaults to a temp dir")
    parser.add_argument(
        "--surface",
        choices=("all", "desktop", "extension"),
        default="all",
        help="surface group to capture",
    )
    return parser.parse_args(argv)


def set_process_dpi_aware() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def assert_image_healthy(path: Path, *, min_width: int = 240, min_height: int = 180) -> tuple[int, int]:
    from PIL import Image, ImageStat

    with Image.open(path) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        if width < min_width or height < min_height:
            raise VisualSmokeError(f"{path.name} is too small: {width}x{height}")

        extrema = rgb.getextrema()
        if all(high - low < 8 for low, high in extrema):
            raise VisualSmokeError(f"{path.name} appears blank: low color range")

        stat = ImageStat.Stat(rgb)
        if max(stat.stddev) < 2.0:
            raise VisualSmokeError(f"{path.name} appears blank: low variance")

        sample = rgb.resize((min(width, 180), min(height, 180)))
        pixels = sample.get_flattened_data() if hasattr(sample, "get_flattened_data") else sample.getdata()
        if len(set(pixels)) < 16:
            raise VisualSmokeError(f"{path.name} appears blank: too few colors")

        return width, height


def collect_tk_text(widget) -> str:
    parts: list[str] = []

    def visit(current) -> None:
        try:
            text = current.cget("text")
            if text:
                parts.append(str(text))
        except Exception:
            pass

        try:
            if current.winfo_class() == "Text":
                text = current.get("1.0", "end").strip()
                if text:
                    parts.append(text)
            elif current.winfo_class() == "Listbox":
                for index in range(current.size()):
                    parts.append(str(current.get(index)))
            elif current.winfo_class() == "Canvas":
                for item in current.find_all():
                    if current.type(item) == "text":
                        text = current.itemcget(item, "text")
                        if text:
                            parts.append(str(text))
        except Exception:
            pass

        try:
            if current.winfo_class() == "Treeview":
                for item in current.get_children(""):
                    parts.extend(str(value) for value in current.item(item, "values"))
        except Exception:
            pass

        try:
            children = current.winfo_children()
        except Exception:
            children = []
        for child in children:
            visit(child)

    visit(widget)
    return "\n".join(parts)


def require_text(surface: str, text_blob: str, expected: Iterable[str]) -> None:
    missing = [text for text in expected if text not in text_blob]
    if missing:
        raise VisualSmokeError(f"{surface} is missing expected text: {', '.join(missing)}")


def capture_tk_window(window, output_dir: Path, name: str, expected_text: Iterable[str]) -> CaptureResult:
    from PIL import ImageGrab

    try:
        window.deiconify()
    except Exception:
        pass
    try:
        window.attributes("-topmost", True)
    except Exception:
        pass
    for _ in range(12):
        window.update_idletasks()
        window.lift()
        try:
            window.focus_force()
        except Exception:
            pass
        window.update()
        if window.winfo_ismapped():
            break
        time.sleep(0.1)
    time.sleep(0.35)
    window.update()

    x = window.winfo_rootx()
    y = window.winfo_rooty()
    width = window.winfo_width()
    height = window.winfo_height()
    if width < 240 or height < 180:
        raise VisualSmokeError(f"{name} window is too small: {width}x{height}")

    text_blob = collect_tk_text(window)
    require_text(name, text_blob, expected_text)

    output_path = output_dir / f"{name}.png"
    image = ImageGrab.grab(bbox=(x, y, x + width, y + height))
    image.save(output_path)
    try:
        window.attributes("-topmost", False)
    except Exception:
        pass
    width, height = assert_image_healthy(output_path)
    return CaptureResult(name, output_path, width, height)


def destroy_window(window) -> None:
    try:
        window.grab_release()
    except Exception:
        pass
    try:
        window.destroy()
    except Exception:
        pass


def run_desktop_smoke(output_dir: Path, data_dir: Path) -> list[CaptureResult]:
    set_process_dpi_aware()
    os.environ["BOOKMARK_DATA_DIR"] = str(data_dir)

    import tkinter as tk

    from bookmark_organizer_pro.app import FinalBookmarkOrganizerApp
    from bookmark_organizer_pro.app_mixins.import_export import ImportProgressModal
    from bookmark_organizer_pro.constants import APP_DIR, ensure_directories
    from bookmark_organizer_pro.models import Bookmark
    from bookmark_organizer_pro.services.reader_annotations import ReaderAnnotationStore
    from bookmark_organizer_pro.services.snapshot import SnapshotBackendAttempt, SnapshotFailureStore
    from bookmark_organizer_pro.theme_runtime import get_theme_manager
    from bookmark_organizer_pro.ui.graph_view import GraphViewDialog
    from bookmark_organizer_pro.ui.cleanup_review import CleanupReviewDialog, CleanupReviewGroup
    from bookmark_organizer_pro.ui.read_later_queue import ReadLaterQueueDialog
    from bookmark_organizer_pro.ui.reader_view import ReaderViewDialog
    from bookmark_organizer_pro.ui.workflow_selective_export import SelectiveExportDialog

    ensure_directories()
    root = tk.Tk()
    root.geometry("1360x860+40+40")
    root.title("Bookmark Organizer Pro Visual Smoke")
    app = FinalBookmarkOrganizerApp(root)
    root.update()

    results: list[CaptureResult] = []
    try:
        results.append(
            capture_tk_window(
                root,
                output_dir,
                "desktop-main-empty-dark",
                ("Bookmark Organizer Pro", "EMPTY LIBRARY", "Start With an Import"),
            )
        )

        sample_bookmarks = [
            Bookmark(
                id=501,
                url="https://example.com/visual-regression",
                title="Visual Regression Guide",
                category="Development",
                tags=["qa", "desktop"],
                is_pinned=True,
                read_later=True,
            ),
            Bookmark(
                id=502,
                url="https://docs.python.org/3/library/tkinter.html",
                title="Tkinter Reference",
                category="Development",
                tags=["python"],
            ),
            Bookmark(
                id=503,
                url="https://developer.chrome.com/docs/extensions",
                title="Extension Platform Notes",
                category="Browsers",
                tags=["extension"],
            ),
        ]
        for bookmark in sample_bookmarks:
            app.bookmark_manager.add_bookmark(bookmark, save=False)
        app.bookmark_manager.save_bookmarks()
        app._refresh_all()

        theme_manager = get_theme_manager()
        theme_manager.set_theme("github_light")
        app._apply_theme_live()
        root.update()
        results.append(
            capture_tk_window(
                root,
                output_dir,
                "desktop-main-list-light",
                ("Bookmark Organizer Pro", "Bookmark"),
            )
        )

        SnapshotFailureStore().record_failure(
            sample_bookmarks[1],
            "All snapshot backends failed",
            (SnapshotBackendAttempt("python", False, "fetch failed: visual smoke"),),
        )
        app._refresh_all()
        root.update()
        results.append(
            capture_tk_window(
                root,
                output_dir,
                "desktop-snapshot-failures-sidebar",
                ("Snapshot Failures", "Review 1 retryable", "Tkinter Reference"),
            )
        )

        theme_manager.set_theme("github_dark")
        app._apply_theme_live()
        root.update()
        app._show_ai_settings()
        assistant = root.winfo_children()[-1]
        results.append(
            capture_tk_window(
                assistant,
                output_dir,
                "desktop-assistant-settings",
                ("Assistant Settings", "Provider", "Model", "Ollama Local"),
            )
        )
        destroy_window(assistant)

        import_modal = ImportProgressModal(root, source_label="visual-smoke.html")
        import_modal.set_progress(12, 40, 8, 4)
        results.append(
            capture_tk_window(
                import_modal,
                output_dir,
                "desktop-import-progress",
                ("Importing from visual-smoke.html", "Processing bookmark", "added"),
            )
        )
        destroy_window(import_modal)

        cleanup_dialog = CleanupReviewDialog(
            root,
            title="Duplicate Review",
            intro="Select duplicate groups to remove. A safepoint is created before changes.",
            groups=[
                CleanupReviewGroup(
                    key="visual-duplicate",
                    title="example.com/article",
                    subtitle="1 duplicate bookmark will be removed; earliest item is kept.",
                    items=(
                        "Keep #501: Visual Regression Guide - https://example.com/visual-regression",
                        "Remove #505: Visual Regression Copy - https://example.com/visual-regression?utm_source=x",
                    ),
                    action_label="Remove 1 duplicate",
                ),
                CleanupReviewGroup(
                    key="visual-tags",
                    title="Normalize to 'python'",
                    subtitle="2 bookmarks affected; 1 variant tag.",
                    items=("Merge 'Python' -> 'python'",),
                    action_label="Merge 1 variant",
                ),
            ],
            on_apply=lambda keys: f"Applied {len(keys)} selected group(s).",
            on_restore=lambda: True,
        )
        results.append(
            capture_tk_window(
                cleanup_dialog,
                output_dir,
                "desktop-cleanup-review",
                ("Duplicate Review", "Apply Selected", "Restore Safepoint", "Remove #505"),
            )
        )
        destroy_window(cleanup_dialog)

        read_later_dialog = ReadLaterQueueDialog(
            root,
            bookmark_manager=app.bookmark_manager,
            on_changed=app._refresh_all,
            on_open_url=lambda _url: True,
        )
        results.append(
            capture_tk_window(
                read_later_dialog,
                output_dir,
                "desktop-read-later-queue",
                ("Read Later Queue", "Open Next", "Mark Done", "Visual Regression Guide"),
            )
        )
        destroy_window(read_later_dialog)

        export_dialog = SelectiveExportDialog(root, app.bookmark_manager)
        results.append(
            capture_tk_window(
                export_dialog,
                output_dir,
                "desktop-export-dialog",
                ("Export Bookmarks", "Export Format", "Categories"),
            )
        )
        destroy_window(export_dialog)

        article_text = (
            "Visual regression checks keep premium desktop surfaces honest. "
            "They catch blank captures, missing labels, and controls that drift "
            "outside their expected frame before release packaging."
        )
        extracted_path = APP_DIR / "extracted" / "visual-smoke-reader.txt"
        extracted_path.parent.mkdir(parents=True, exist_ok=True)
        extracted_path.write_text(article_text, encoding="utf-8")
        reader_bookmark = Bookmark(
            id=504,
            url="https://example.com/reader",
            title="Reader QA Notes",
            category="Research",
            extracted_text_path=str(extracted_path),
        )
        reader_store = ReaderAnnotationStore(APP_DIR / "reader_annotations_visual.json")
        reader_store.add_from_text(504, article_text, 0, 25, color="yellow", note="Visual smoke highlight")
        reader_dialog = ReaderViewDialog(root, reader_bookmark, store=reader_store)
        results.append(
            capture_tk_window(
                reader_dialog,
                output_dir,
                "desktop-reader-view",
                ("Reader QA Notes", "Highlights", "Select text in the reader"),
            )
        )
        destroy_window(reader_dialog)

        graph_dialog = GraphViewDialog(root, sample_bookmarks)
        results.append(
            capture_tk_window(
                graph_dialog,
                output_dir,
                "desktop-graph-view",
                ("Bookmark Graph", "Legend", "Selected"),
            )
        )
        destroy_window(graph_dialog)
    finally:
        try:
            app._on_close()
        except Exception:
            destroy_window(root)

    return results


def extension_init_script() -> str:
    return """
(() => {
  const config = { apiPort: 8765, apiToken: "visual-token", defaultCategory: "Research" };
  const activeTab = { id: 42, url: "https://example.com/visual-regression", title: "Visual QA Handbook" };
  const storageArea = {
    get(keys, callback) {
      const values = { ...config };
      if (typeof callback === "function") { callback(values); return undefined; }
      return Promise.resolve(values);
    },
    set(values, callback) {
      Object.assign(config, values || {});
      if (typeof callback === "function") callback();
      return Promise.resolve();
    }
  };
  const api = {
    storage: { local: storageArea },
    tabs: {
      query(queryInfo, callback) {
        if (typeof callback === "function") { callback([activeTab]); return undefined; }
        return Promise.resolve([activeTab]);
      },
      onActivated: { addListener() {} }
    },
    scripting: {
      executeScript(details, callback) {
        const result = [{ result: "Selected passage from the active page." }];
        if (typeof callback === "function") { callback(result); return undefined; }
        return Promise.resolve(result);
      }
    },
    readingList: {
      query() {
        return Promise.resolve([{ url: "https://example.com/read-later", title: "Read Later Item", hasBeenRead: false }]);
      }
    },
    runtime: {
      lastError: null,
      getURL(path) { return `http://127.0.0.1:8765/__extension/${path}`; },
      openOptionsPage(callback) {
        if (typeof callback === "function") callback();
        return Promise.resolve();
      }
    }
  };
  window.chrome = api;
  window.browser = api;
})();
"""


def fulfill_api(route) -> None:
    url = route.request.url
    sample_bookmarks = [
        {
            "id": 501,
            "url": "https://example.com/visual-regression",
            "title": "Visual QA Handbook",
            "category": "Research",
        },
        {
            "id": 502,
            "url": "https://docs.python.org/3/library/tkinter.html",
            "title": "Tkinter Reference",
            "category": "Development",
        },
    ]
    if "/__extension/categories.json" in url:
        payload = ["Research", "Development", "Browsers", "Read Later"]
    elif "/stats" in url:
        payload = {"total_bookmarks": len(sample_bookmarks)}
    elif "/digest" in url:
        payload = {"sections": [{"title": "Rediscover", "bookmarks": sample_bookmarks[:1]}]}
    elif "/search" in url:
        payload = {"results": sample_bookmarks}
    elif "/bookmarks" in url and route.request.method == "POST":
        payload = {"id": 999, "status": "created"}
        route.fulfill(status=201, content_type="application/json", body=json.dumps(payload))
        return
    elif "/bookmarks" in url:
        payload = {"bookmarks": sample_bookmarks}
    else:
        payload = {"name": "Bookmark Organizer Pro", "version": "6.9.0"}
    route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))


def check_browser_layout(page, surface: ExtensionSurface) -> None:
    body_text = page.locator("body").inner_text(timeout=5000)
    require_text(surface.name, body_text, surface.expected_text)
    overflow = page.evaluate(
        """() => ({
            scrollWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
            clientWidth: document.documentElement.clientWidth
        })"""
    )
    if overflow["scrollWidth"] > overflow["clientWidth"] + 1:
        raise VisualSmokeError(
            f"{surface.name} has horizontal overflow: {overflow['scrollWidth']} > {overflow['clientWidth']}"
        )


def run_extension_smoke(output_dir: Path) -> list[CaptureResult]:
    from playwright.sync_api import sync_playwright

    results: list[CaptureResult] = []
    errors: list[str] = []
    extension_dir = ROOT / "browser-extension"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for surface in EXTENSION_SURFACES:
                context = browser.new_context(
                    viewport={"width": surface.viewport[0], "height": surface.viewport[1]},
                    color_scheme=surface.color_scheme,
                )
                context.add_init_script(extension_init_script())
                context.route("http://127.0.0.1:8765/**", fulfill_api)
                page = context.new_page()
                page.on("console", lambda message: errors.append(f"{surface.name}: {message.text}") if message.type == "error" else None)
                page.on("pageerror", lambda error: errors.append(f"{surface.name}: {error}"))
                page.goto((extension_dir / surface.html_file).as_uri(), wait_until="domcontentloaded")
                if surface.click_selector:
                    page.locator(surface.click_selector).click()
                page.wait_for_timeout(350)
                check_browser_layout(page, surface)
                output_path = output_dir / f"{surface.name}.png"
                page.screenshot(path=str(output_path), full_page=False)
                width, height = assert_image_healthy(
                    output_path,
                    min_width=min(240, surface.viewport[0]),
                    min_height=min(180, surface.viewport[1]),
                )
                results.append(CaptureResult(surface.name, output_path, width, height))
                context.close()
        finally:
            browser.close()

    if errors:
        raise VisualSmokeError("Extension console/page errors:\n" + "\n".join(errors))
    return results


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    temp_data = None
    if args.data_dir:
        data_dir = args.data_dir.resolve()
    else:
        temp_data = tempfile.TemporaryDirectory(prefix="bop-visual-data-", ignore_cleanup_errors=True)
        data_dir = Path(temp_data.name).resolve()

    try:
        results: list[CaptureResult] = []
        if args.surface in {"all", "desktop"}:
            results.extend(run_desktop_smoke(output_dir, data_dir))
        if args.surface in {"all", "extension"}:
            results.extend(run_extension_smoke(output_dir))

        summary = {
            "output_dir": str(output_dir),
            "captures": [
                {"name": result.name, "path": str(result.path), "width": result.width, "height": result.height}
                for result in results
            ],
        }
        print(json.dumps(summary, indent=2))
        return 0
    except VisualSmokeError as exc:
        print(f"visual smoke failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if temp_data is not None:
            temp_data.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
