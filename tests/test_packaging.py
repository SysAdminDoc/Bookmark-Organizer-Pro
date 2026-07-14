"""Packaging helper tests."""

from __future__ import annotations

import importlib.util
import json
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


def _load_package_contract_audit():
    path = ROOT / "scripts" / "package_contract_audit.py"
    spec = importlib.util.spec_from_file_location("bop_package_contract_audit", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_release_builder():
    path = ROOT / "scripts" / "build_release.py"
    spec = importlib.util.spec_from_file_location("bop_release_builder", path)
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
            version="6.6.22",
            root=ROOT,
        )

        self.assertEqual(command[:3], ["python", "-m", "nuitka"])
        self.assertIn("--mode=onefile", command)
        self.assertIn("--enable-plugin=tk-inter", command)
        self.assertIn("--include-package=bookmark_organizer_pro", command)
        self.assertIn("--jobs=4", command)
        self.assertIn("--file-version=6.6.22.0", command)
        self.assertIn("--product-version=6.6.22.0", command)
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

        command = module.build_command(jobs=2, version="6.6.22", root=ROOT)

        self.assertIn("--jobs=2", command)

    def test_smoke_target_uses_console_entrypoint(self):
        module = _load_nuitka_build()

        command = module.build_command(target="smoke", version="6.6.22", root=ROOT)

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

    def test_vulnerable_updater_is_not_in_release_extras(self):
        pyproject_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertNotIn('updates = ["tufup', pyproject_text)
        self.assertNotIn("mcp,updates,sunvalley", pyproject_text)

    def test_sunvalley_extra_is_declared(self):
        pyproject_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('sunvalley = ["sv-ttk>=2.6.1,<3.0"]', pyproject_text)

    def test_release_collector_excludes_optional_upstream_mcp_cli(self):
        spec_text = (ROOT / "packaging" / "bookmark_organizer.spec").read_text(encoding="utf-8")

        self.assertIn('name != "mcp.cli"', spec_text)
        self.assertIn("filter_submodules=release_submodule_filter", spec_text)
        self.assertNotIn("'numpy',", spec_text)
        self.assertNotIn("'pydoc',", spec_text)

    def test_updater_bootstrap_doc_covers_trusted_root_and_target_name(self):
        doc_path = ROOT / "docs" / "distribution" / "updater-bootstrap.md"
        if not doc_path.exists():
            self.skipTest("local updater bootstrap documentation is intentionally untracked")
        doc = doc_path.read_text(encoding="utf-8")

        self.assertIn("updates/metadata/root.json", doc)
        self.assertIn("BookmarkOrganizerPro-6.6.11.tar.gz", doc)
        self.assertIn("updates download", doc)
        self.assertIn("updates apply", doc)

    def test_distribution_docs_are_local_only(self):
        durable_docs = [
            ROOT / "README.md",
            ROOT / "ROADMAP.md",
        ]
        structure_doc = ROOT / "docs" / "REPOSITORY_STRUCTURE.md"
        if structure_doc.exists():
            durable_docs.append(structure_doc)
        for path in durable_docs:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(".github/workflows", text, path)
            self.assertNotIn("GitHub Actions", text, path)
        if structure_doc.exists():
            structure = structure_doc.read_text(encoding="utf-8")
            self.assertIn("python -m pytest -q", structure)
            self.assertIn("scripts/release_artifact_smoke.py", structure)

    def test_unshipped_placeholder_ui_paths_are_removed(self):
        removed_modules = [
            ROOT / "bookmark_organizer_pro" / "ui" / "drag_drop.py",
            ROOT / "bookmark_organizer_pro" / "ui" / "widget_grid.py",
            ROOT / "bookmark_organizer_pro" / "ui" / "widget_lists.py",
            ROOT / "bookmark_organizer_pro" / "ui" / "widget_tray.py",
        ]
        for path in removed_modules:
            self.assertFalse(path.exists(), path)

        navigation = (ROOT / "bookmark_organizer_pro" / "ui" / "navigation.py").read_text(encoding="utf-8")
        self.assertNotIn("_visual_mode_toggle", navigation)
        self.assertNotIn("'v':", navigation)

        package_surfaces = [
            ROOT / "README.md",
            ROOT / "requirements.txt",
            ROOT / "pyproject.toml",
            ROOT / "packaging" / "bookmark_organizer.spec",
            ROOT / "scripts" / "build_windows.bat",
            ROOT / "scripts" / "build_unix.sh",
        ]
        for path in package_surfaces:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("pystray", text, path)
            self.assertNotIn("System Tray", text, path)

    def test_release_dependencies_are_generated_from_pyproject_and_locked(self):
        module = _load_package_contract_audit()

        report = module.validate_dependency_contract()

        self.assertGreater(report["direct_dependencies"], 10)
        install_lines = [
            line.strip()
            for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")
        ]
        self.assertEqual(install_lines, [module.INSTALL_LINE])

    def test_release_lock_renders_hash_required_install_input(self):
        module = _load_package_contract_audit()

        requirements = module.locked_requirements_text()

        self.assertIn("lz4==4.4.5 --hash=sha256:", requirements)
        self.assertNotIn("bookmark-organizer-pro==", requirements)
        self.assertTrue(all("--hash=sha256:" in line for line in requirements.splitlines()))

    def test_release_manifest_declares_frozen_runtime_capabilities(self):
        module = _load_package_contract_audit()

        report = module.validate_dependency_contract()
        manifest = json.loads(module.RELEASE_MANIFEST.read_text(encoding="utf-8"))
        capabilities = {item["name"]: item for item in manifest["runtime_capabilities"]}

        self.assertGreater(report["locked_dependencies"], 100)
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(manifest["release_profile"], "all")
        self.assertEqual(capabilities["firefox_jsonlz4"]["distribution"], "lz4")
        self.assertIn("default_categories", capabilities)

    def test_release_builder_uses_platform_specific_venv_python(self):
        module = _load_release_builder()

        self.assertEqual(module.venv_python(Path("env"), "win32"), Path("env/Scripts/python.exe"))
        self.assertEqual(module.venv_python(Path("env"), "linux"), Path("env/bin/python"))

    def test_pyinstaller_runtime_hook_guards_multiprocessing(self):
        spec_text = (ROOT / "packaging" / "bookmark_organizer.spec").read_text(encoding="utf-8")
        hook_text = (ROOT / "packaging" / "runtime_hook_multiprocessing.py").read_text(
            encoding="utf-8"
        )

        self.assertIn('RUNTIME_HOOK_MP = SPEC_DIR / "runtime_hook_multiprocessing.py"', spec_text)
        self.assertIn("runtime_hooks=[str(RUNTIME_HOOK_MP)]", spec_text)
        self.assertIn("multiprocessing.freeze_support()", hook_text)
        self.assertIn('"bookmark_organizer_pro/core"', spec_text)
        self.assertIn('"release"', spec_text)

    def test_public_product_counts_match_live_surfaces(self):
        module = _load_package_contract_audit()

        self.assertEqual(module.validate_product_claims(), module.live_product_claims())


if __name__ == "__main__":
    unittest.main()
