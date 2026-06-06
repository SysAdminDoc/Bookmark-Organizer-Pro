"""Packaging helper tests."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def _load_nuitka_build():
    path = ROOT / "packaging" / "nuitka_build.py"
    spec = importlib.util.spec_from_file_location("bop_nuitka_build", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_nuitka_smoke():
    path = ROOT / "packaging" / "nuitka_smoke.py"
    spec = importlib.util.spec_from_file_location("bop_nuitka_smoke", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestNuitkaBuildHelper(unittest.TestCase):
    def test_command_includes_tk_assets_and_version_metadata(self):
        module = _load_nuitka_build()

        command = module.build_command(
            mode="onefile",
            output_dir=Path("dist/nuitka"),
            python_executable="python",
            version="6.6.12",
            root=ROOT,
        )

        self.assertEqual(command[:3], ["python", "-m", "nuitka"])
        self.assertIn("--mode=onefile", command)
        self.assertIn("--enable-plugin=tk-inter", command)
        self.assertIn("--include-package=bookmark_organizer_pro", command)
        self.assertIn("--jobs=4", command)
        self.assertIn("--file-version=6.6.12.0", command)
        self.assertIn("--product-version=6.6.12.0", command)
        self.assertTrue(any(arg.startswith("--include-data-files=") for arg in command))
        self.assertEqual(command[-1], str(ROOT / "main.py"))

    def test_dry_run_prints_command_without_subprocess(self):
        module = _load_nuitka_build()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(sys, "argv", ["nuitka_build.py"]):
                with patch("subprocess.call") as call:
                    result = module.main(["--dry-run", "--output-dir", tmp, "--jobs", "2"])

        self.assertEqual(result, 0)
        call.assert_not_called()

    def test_command_accepts_custom_jobs(self):
        module = _load_nuitka_build()

        command = module.build_command(jobs=2, version="6.6.12", root=ROOT)

        self.assertIn("--jobs=2", command)

    def test_smoke_target_uses_console_entrypoint(self):
        module = _load_nuitka_build()

        command = module.build_command(target="smoke", version="6.6.12", root=ROOT)

        self.assertIn("--output-filename=BookmarkOrganizerProSmoke", command)
        self.assertFalse(any(arg.startswith("--include-module=") for arg in command))
        self.assertNotIn("--include-package=bookmark_organizer_pro", command)
        if sys.platform.startswith("win"):
            self.assertIn("--windows-console-mode=force", command)
        self.assertEqual(command[-1], str(ROOT / "packaging" / "nuitka_smoke.py"))

    def test_smoke_entrypoint_version_matches_app(self):
        from bookmark_organizer_pro.constants import APP_NAME, APP_VERSION

        module = _load_nuitka_smoke()

        self.assertEqual(module.APP_NAME, APP_NAME)
        self.assertEqual(module.APP_VERSION, APP_VERSION)

    def test_nuitka_extra_is_declared(self):
        pyproject_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('nuitka = ["Nuitka>=4.1,<5.0"]', pyproject_text)

    def test_updates_extra_is_declared(self):
        pyproject_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('updates = ["tufup>=0.10,<0.11"]', pyproject_text)
        self.assertIn('"bookmark-organizer-pro[tray,ai,encryption,mcp,updates]"', pyproject_text)

    def test_updater_bootstrap_doc_covers_trusted_root_and_target_name(self):
        doc = (ROOT / "docs" / "distribution" / "updater-bootstrap.md").read_text(encoding="utf-8")

        self.assertIn("updates/metadata/root.json", doc)
        self.assertIn("BookmarkOrganizerPro-6.6.11.tar.gz", doc)
        self.assertIn("updates download", doc)
        self.assertIn("updates apply", doc)


if __name__ == "__main__":
    unittest.main()
