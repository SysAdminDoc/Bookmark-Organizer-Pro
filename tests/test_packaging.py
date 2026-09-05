"""Packaging helper tests."""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
import re
import shutil
import tomllib
import subprocess
import sys
import tempfile
import unittest
import zipfile
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


def _load_extension_builder():
    path = ROOT / "scripts" / "build_extension.py"
    spec = importlib.util.spec_from_file_location("bop_extension_builder", path)
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
        self.assertIn(
            f"--include-data-files={ROOT / 'bookmark_organizer_pro' / 'bootstrap_dependencies.json'}="
            "bookmark_organizer_pro/bootstrap_dependencies.json",
            command,
        )
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

    def test_bootstrap_manifest_matches_every_required_pyproject_dependency(self):
        module = _load_package_contract_audit()
        checked_in = json.loads(module.BOOTSTRAP_MANIFEST.read_text(encoding="utf-8"))
        project_data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertEqual(checked_in, module.bootstrap_manifest_document())
        self.assertEqual(module.validate_bootstrap_manifest(), 10)
        self.assertEqual(
            {entry["import_name"] for entry in checked_in["dependencies"]},
            {"bs4", "requests", "idna", "PIL", "defusedxml", "tksheet", "urllib3", "lxml", "lz4", "regex"},
        )
        self.assertEqual(project_data["tool"]["setuptools"]["py-modules"], ["bootstrap_dependencies"])
        self.assertIn(
            "**/*.json",
            project_data["tool"]["setuptools"]["package-data"]["bookmark_organizer_pro"],
        )

    def test_security_relevant_dependency_floors_stay_at_or_above_the_fixed_release(self):
        """R-177: these fixes carry no CVE, so pip-audit cannot hold this line.

        lxml 6.1.3 stops external parameter entities being parsed by default
        even under resolve_entities="internal", regex 2026.8.31 is the published
        build of the four memory-safety fixes listed under 2026.8.30 (that
        version was never released to PyPI), and mcp 1.29.1 applies the 4 MiB
        request body limit to the SSE and OAuth endpoints. All three parse or
        compile input this project takes from users.
        """
        project_data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        requirements = list(project_data["project"]["dependencies"])
        for group in project_data["project"]["optional-dependencies"].values():
            requirements.extend(group)

        floors = {}
        for requirement in requirements:
            name, separator, rest = requirement.partition(">=")
            if not separator:
                continue
            floors[name.strip().lower()] = rest.split(",")[0].strip()

        required = {"lxml": (6, 1, 3), "regex": (2026, 8, 31), "mcp": (1, 29, 1)}
        for name, minimum in required.items():
            with self.subTest(dependency=name):
                self.assertIn(name, floors, f"{name} lost its lower bound")
                declared = tuple(int(part) for part in floors[name].split("."))
                self.assertGreaterEqual(
                    declared,
                    minimum,
                    f"{name} floor {floors[name]} is below the release that fixed it",
                )

    def test_bootstrap_module_imports_only_the_standard_library(self):
        tree = ast.parse((ROOT / "bootstrap_dependencies.py").read_text(encoding="utf-8"))
        imported_roots = set()
        process_calls = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".", 1)[0])
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "subprocess"
            ):
                process_calls.add(node.func.attr)

        self.assertLessEqual(imported_roots, set(sys.stdlib_module_names) | {"__future__"})
        self.assertEqual(process_calls, {"list2cmdline"})

    def test_main_preflight_reports_each_missing_import_before_package_import(self):
        module = _load_package_contract_audit()
        manifest = module.bootstrap_manifest_document()
        probe = """
import importlib.util
import runpy
import sys

target = sys.argv[1]
original_find_spec = importlib.util.find_spec

class ApplicationImportGuard:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "bookmark_organizer_pro" or fullname.startswith("bookmark_organizer_pro."):
            raise RuntimeError("application package imported before dependency preflight")
        return None

sys.meta_path.insert(0, ApplicationImportGuard())
importlib.util.find_spec = lambda name, package=None: (
    None if name == target else original_find_spec(name, package)
)
runpy.run_path(sys.argv[2], run_name="__main__")
"""
        for dependency in manifest["dependencies"]:
            import_name = dependency["import_name"]
            result = subprocess.run(
                [sys.executable, "-c", probe, import_name, str(ROOT / "main.py")],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            with self.subTest(import_name=import_name):
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(import_name, result.stderr)
                self.assertIn(sys.executable, result.stderr)
                self.assertIn("-m pip install --upgrade --force-reinstall", result.stderr)
                self.assertIn(str(ROOT), result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_frozen_bootstrap_guidance_uses_complete_signed_release(self):
        from bootstrap_dependencies import COMPLETE_RELEASE_URL, repair_message

        message = repair_message(("regex",), frozen=True)

        self.assertIn("regex", message)
        self.assertIn("complete signed release", message)
        self.assertIn(COMPLETE_RELEASE_URL, message)
        self.assertNotIn(" -m pip ", message)

    def test_nuitka_runtime_uses_compiled_module_path_and_frozen_guidance(self):
        import bootstrap_dependencies as bootstrap

        with tempfile.TemporaryDirectory() as tmp:
            bundle_root = Path(tmp) / "onefile"
            with (
                patch.object(bootstrap, "__compiled__", object(), create=True),
                patch.object(
                    bootstrap,
                    "__file__",
                    str(bundle_root / "bootstrap_dependencies.py"),
                ),
            ):
                self.assertTrue(bootstrap.is_frozen_runtime())
                self.assertEqual(
                    bootstrap.manifest_path(),
                    bundle_root
                    / "bookmark_organizer_pro"
                    / "bootstrap_dependencies.json",
                )
                message = bootstrap.repair_message(("regex",))

        self.assertIn("complete signed release", message)
        self.assertNotIn(" -m pip ", message)

    def test_importing_the_package_never_exits_the_process(self):
        probe = """
import bookmark_organizer_pro
import bookmark_organizer_pro.cli
import bookmark_organizer_pro.mcp_server
print("imported")
"""
        result = subprocess.run(
            [sys.executable, "-c", probe],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("imported", result.stdout)

    def test_package_facade_does_not_call_the_dependency_preflight(self):
        tree = ast.parse((ROOT / "bookmark_organizer_pro" / "__init__.py").read_text(encoding="utf-8"))
        called = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }

        self.assertNotIn("preflight_or_exit", called)
        self.assertNotIn("_preflight_or_exit", called)

    def test_console_scripts_preflight_before_importing_the_package(self):
        """A genuinely absent dependency must reach the guidance, not a traceback.

        Patching importlib.util.find_spec is not enough here: it does not
        affect the real import system, so the application package still imports
        and only the preflight sees the fake absence. This blocks the module on
        sys.meta_path, which is how a missing dependency actually behaves, and
        is the condition that proved a preflight living inside main() is
        unreachable for a console script.
        """
        module = _load_package_contract_audit()
        manifest = module.bootstrap_manifest_document()
        project_data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        probe = """
import importlib
import sys

blocked, target, attribute = sys.argv[1], sys.argv[2], sys.argv[3]


class Blocker:
    def find_spec(self, fullname, path=None, target=None):
        if fullname == blocked or fullname.startswith(blocked + "."):
            raise ModuleNotFoundError(f"No module named {fullname!r}", name=fullname)
        return None


sys.meta_path.insert(0, Blocker())
entry = getattr(importlib.import_module(target), attribute)
raise SystemExit(entry())
"""
        for script, declared in sorted(project_data["project"]["scripts"].items()):
            target, _, attribute = declared.partition(":")
            for dependency in manifest["dependencies"]:
                import_name = dependency["import_name"]
                result = subprocess.run(
                    [sys.executable, "-c", probe, import_name, target, attribute],
                    cwd=ROOT,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    check=False,
                )
                with self.subTest(script=script, import_name=import_name):
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn(import_name, result.stderr)
                    self.assertIn(sys.executable, result.stderr)
                    self.assertIn("-m pip install --upgrade --force-reinstall", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)
                    self.assertNotIn("ModuleNotFoundError", result.stderr)

    def test_console_scripts_route_through_the_stdlib_only_bootstrap(self):
        project_data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        for script, declared in project_data["project"]["scripts"].items():
            with self.subTest(script=script):
                self.assertTrue(
                    declared.startswith("bootstrap_dependencies:"),
                    f"{script} imports the application package before the preflight can run",
                )

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
        self.assertIn('"bootstrap_dependencies.json"', spec_text)
        self.assertIn('"release"', spec_text)


class TestExtensionDistribution(unittest.TestCase):
    def test_chromium_and_firefox_manifests_have_explicit_parity_and_api_differences(self):
        module = _load_extension_builder()
        chromium = module.load_manifest("chromium")
        firefox = module.load_manifest("firefox")

        module.validate_manifest("chromium", chromium)
        module.validate_manifest("firefox", firefox)
        module.validate_parity(chromium, firefox)
        self.assertEqual(chromium["background"], {"service_worker": "background.js"})
        self.assertEqual(firefox["background"]["scripts"][-1], "background.js")
        self.assertEqual(firefox["sidebar_action"]["default_panel"], "sidepanel.html")
        self.assertNotIn("sidePanel", firefox["permissions"])
        self.assertNotIn("readingList", firefox["permissions"])
        self.assertIn("browser_specific_settings", firefox)

    def test_mcp_registry_manifest_tracks_the_app_version(self):
        from bookmark_organizer_pro.constants import APP_VERSION

        module = _load_package_contract_audit()
        document = module.validate_mcp_server_json()

        self.assertEqual(document["version"], APP_VERSION)
        self.assertEqual(document["name"], "io.github.sysadmindoc/bookmark-organizer-pro")
        self.assertEqual(document["packages"][0]["identifier"], "bookmark-organizer-pro")
        self.assertEqual(document["packages"][0]["transport"]["type"], "stdio")
        self.assertLessEqual(len(document["description"]), 100)

        # The declared launch command must name a console script that exists,
        # or the registry entry installs and then fails to start.
        pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        scripts = pyproject["project"]["scripts"]
        declared = [
            argument["value"]
            for argument in document["packages"][0]["runtimeArguments"]
            if argument["type"] == "positional"
        ]
        self.assertEqual(declared, ["bop-mcp"])
        self.assertIn("bop-mcp", scripts)

        broken = copy.deepcopy(document)
        broken["packages"][0]["runtimeArguments"] = [
            {"type": "positional", "valueHint": "console_script", "value": "not-a-script"}
        ]
        original = module.MCP_SERVER_JSON.read_text(encoding="utf-8")
        try:
            module.MCP_SERVER_JSON.write_text(json.dumps(broken), encoding="utf-8")
            with self.assertRaises(module.ContractError):
                module.validate_mcp_server_json()
        finally:
            module.MCP_SERVER_JSON.write_text(original, encoding="utf-8")

        original = module.MCP_SERVER_JSON.read_text(encoding="utf-8")
        stale = json.loads(original)
        stale["version"] = "0.0.1"
        try:
            module.MCP_SERVER_JSON.write_text(json.dumps(stale), encoding="utf-8")
            with self.assertRaises(module.ContractError):
                module.validate_mcp_server_json()
        finally:
            module.MCP_SERVER_JSON.write_text(original, encoding="utf-8")

    def test_firefox_version_floors_match_the_data_collection_key(self):
        """R-137. The disclosure key was declared under strict_min_version 121,
        which web-ext rejects outright on the pinned version and warns about on
        current ones, because Firefox only reads the key from 140 and Firefox
        for Android from 142. The gate never caught it: the Firefox smoke is not
        part of the suite, and the pinned web-ext was old enough that the whole
        lint failed on a different error first."""
        module = _load_extension_builder()
        firefox = module.load_manifest("firefox")
        settings = firefox["browser_specific_settings"]

        self.assertGreaterEqual(
            module._version_tuple(settings["gecko"]["strict_min_version"]),
            module.DATA_COLLECTION_MIN_DESKTOP,
        )
        self.assertGreaterEqual(
            module._version_tuple(settings["gecko_android"]["strict_min_version"]),
            module.DATA_COLLECTION_MIN_ANDROID,
        )

        for broken in (
            {"gecko": {"strict_min_version": "121.0"}, "gecko_android": {"strict_min_version": "142.0"}},
            {"gecko": {"strict_min_version": "140.0"}},
            {"gecko": {"strict_min_version": "140.0"}, "gecko_android": {"strict_min_version": "141.0"}},
        ):
            with self.subTest(broken=broken), self.assertRaises(ValueError):
                module.validate_data_collection_floors(broken)

        module.validate_data_collection_floors(settings)

    def test_firefox_smoke_pins_a_web_ext_that_knows_the_disclosure_key(self):
        """web-ext 8.9.0 called data_collection_permissions reserved and failed
        the whole lint, so the Firefox gate had been red since the key landed."""
        source = (
            Path(__file__).resolve().parents[1] / "scripts/extension_firefox_smoke.py"
        ).read_text(encoding="utf-8")
        match = re.search(r'WEB_EXT_VERSION = "(\d+)\.(\d+)\.(\d+)"', source)
        self.assertIsNotNone(match, "the smoke must pin an explicit web-ext version")
        major, minor, _patch = (int(part) for part in match.groups())
        self.assertGreaterEqual((major, minor), (10, 0), "web-ext is too old to lint the manifest")

    def test_firefox_manifest_declares_data_collection_consent(self):
        module = _load_extension_builder()
        firefox = module.load_manifest("firefox")
        declared = firefox["browser_specific_settings"]["gecko"]["data_collection_permissions"]

        # Saving always transmits bookmark data to the local API; page content is
        # only sent when the user ticks the per-save snapshot capture box.
        self.assertEqual(declared["required"], ["bookmarksInfo"])
        self.assertEqual(declared["optional"], ["websiteContent"])

        stripped = copy.deepcopy(firefox)
        del stripped["browser_specific_settings"]["gecko"]["data_collection_permissions"]
        with self.assertRaises(ValueError):
            module.validate_manifest("firefox", stripped)

        for invalid in (
            {"required": []},
            {"required": ["none", "bookmarksInfo"]},
            {"required": ["technicalAndInteraction"]},
            {"required": ["notARealDataType"]},
            {"required": ["bookmarksInfo"], "optional": ["none"]},
            {"required": ["bookmarksInfo"], "optional": ["bookmarksInfo"]},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                module.validate_data_collection_permissions(invalid)

        module.validate_data_collection_permissions({"required": ["none"]})
        module.validate_data_collection_permissions(
            {"required": ["bookmarksInfo"], "optional": ["technicalAndInteraction"]}
        )

    def test_extension_builder_emits_deterministic_isolated_artifacts(self):
        module = _load_extension_builder()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "extension"
            first = module.build_target("firefox", output)
            second = module.build_target("firefox", output)
            chromium = module.build_target("chromium", output)

            self.assertEqual(first["sha256"], second["sha256"])
            self.assertTrue(str(first["archive"]).endswith(".xpi"))
            self.assertTrue(str(chromium["archive"]).endswith(".zip"))
            built = Path(str(first["directory"]))
            manifest = json.loads((built / "manifest.json").read_text(encoding="utf-8"))
            self.assertIn("sidebar_action", manifest)
            self.assertFalse((built / "manifest.firefox.json").exists())
            with zipfile.ZipFile(str(first["archive"])) as archive:
                self.assertIn("manifest.json", archive.namelist())
                self.assertNotIn("manifest.firefox.json", archive.namelist())

    def test_firefox_smoke_uses_clean_profile_and_records_runtime_limitation(self):
        smoke = (ROOT / "scripts" / "extension_firefox_smoke.py").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        background = (ROOT / "browser-extension" / "background.js").read_text(encoding="utf-8")

        self.assertIn('PROFILE_MARKER = "Creating new Firefox profile"', smoke)
        self.assertIn('INSTALL_MARKER = "as a temporary add-on"', smoke)
        self.assertNotIn('"--firefox-profile"', smoke)
        self.assertIn('"status": "unavailable"', smoke)
        self.assertIn("chrome.readingList", readme)
        self.assertIn("status 2", readme)
        self.assertIn('typeof importScripts === "function"', background)
        self.assertIn("api.sidebarAction.open", background)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for the extension journal harness")
    def test_extension_save_journal_is_deduplicated_retryable_and_recoverable(self):
        shared = ROOT / "browser-extension" / "shared.js"
        harness = r"""
const fs = require("fs");
const vm = require("vm");
const state = {};
const control = { mode: "503" };
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
const chrome = {
  storage: { local },
  runtime: {
    sendMessage: async message => ({ ok: true, config: { apiPort: 8765, apiToken: "token" } }),
    getURL: path => path
  }
};
const fetch = async () => {
  if (control.mode === "throw") throw new Error("offline");
  return { status: Number(control.mode), json: async () => ({}) };
};
const context = vm.createContext({ chrome, console, fetch, Date, Math, URL, Blob, control });
context.globalThis = context;
vm.runInContext(fs.readFileSync(process.argv[1], "utf8"), context);
vm.runInContext(`(async () => {
  const config = { apiPort: 8765, apiToken: "token" };
  const first = await saveBookmarkPayload(
    { url: "https://example.com", title: "Popup title" }, config, { source: "popup" }
  );
  control.mode = "throw";
  const second = await saveBookmarkPayload(
    { url: "https://example.com", title: "Sidebar title" }, config, { source: "side_panel" }
  );
  const pending = await getPendingSaves();
  let refused = false;
  try { await clearPendingSaves(); } catch { refused = true; }
  const cleared = await clearPendingSaves({ confirmed: true });
  const snapshot = await getClearedPendingSaves();
  const restored = await restoreClearedPendingSaves();
  control.mode = "409";
  const retry = await retryPendingSaves();
  globalThis.result = { first, second, pending, refused, cleared, snapshot, restored, retry,
    remaining: await getPendingSaves() };
})()`, context)
  .then(() => process.stdout.write(JSON.stringify(context.result)))
  .catch(error => { console.error(error); process.exitCode = 1; });
"""
        completed = subprocess.run(
            ["node", "-e", harness, str(shared)],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertTrue(result["first"]["queued"])
        self.assertTrue(result["second"]["queued"])
        self.assertEqual(len(result["pending"]), 1)
        self.assertEqual(result["pending"][0]["source"], "side_panel")
        self.assertEqual(result["pending"][0]["payload"]["title"], "Sidebar title")
        self.assertIn("created_at", result["pending"][0])
        self.assertTrue(result["refused"])
        self.assertEqual((result["cleared"], result["restored"]), (1, 1))
        self.assertEqual(len(result["snapshot"]["items"]), 1)
        self.assertEqual(result["retry"], {"attempted": 1, "resolved": 1, "remaining": 0})
        self.assertEqual(result["remaining"], [])

    def test_extension_queue_ui_exposes_rows_export_confirmation_and_undo(self):
        for name in ("popup.html", "sidepanel.html"):
            html = (ROOT / "browser-extension" / name).read_text(encoding="utf-8")
            for control in ("pendingList", "exportPending", "clearPending", "restorePending"):
                self.assertIn(f'id="{control}"', html)
        for name in ("popup.js", "sidepanel.js"):
            source = (ROOT / "browser-extension" / name).read_text(encoding="utf-8")
            self.assertIn("globalThis.confirm", source)
            self.assertIn("renderPendingSaves", source)
            self.assertIn("exportPendingSaves", source)
            self.assertIn("restoreClearedPendingSaves", source)

    def test_public_product_counts_match_live_surfaces(self):
        module = _load_package_contract_audit()

        self.assertEqual(module.validate_product_claims(), module.live_product_claims())

    def test_desktop_copy_uses_real_plurals_not_the_parenthesised_shorthand(self):
        """"5 bookmark(s)" reads as unfinished product copy. `pluralize` and
        `format_plural` pick the right word, so the shorthand has no reason to
        reappear anywhere a person reads: desktop, CLI, or command history.

        Only string literals are searched. Matching raw lines flagged
        `fromisoformat(s)` and `len(s)`, which are calls, not copy.

        The allowed fragments are strings that are not product copy either: the
        http(s) scheme name, a regex alternation, and the model prompt in the
        citation summarizer, whose wording is tuned and not read by anyone.
        """
        import ast

        root = Path(__file__).resolve().parents[1]
        package = root / "bookmark_organizer_pro"
        allowed_fragments = (
            "http(s)",
            r"paper(s)?",
            "supporting chunk(s) using the form",
        )
        offenders = []

        targets = sorted(package.rglob("*.py"))
        targets.append(root / "scripts" / "visual_regression_smoke.py")
        for source in targets:
            relative = source.relative_to(root).as_posix()
            text = source.read_text(encoding="utf-8")
            if "(s)" not in text:
                continue
            for node in ast.walk(ast.parse(text, filename=relative)):
                if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                    continue
                if "(s)" not in node.value:
                    continue
                if any(fragment in node.value for fragment in allowed_fragments):
                    continue
                offenders.append(f"{relative}:{node.lineno}: {node.value.strip()[:90]}")

        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_no_translatable_string_has_its_noun_built_in_python(self):
        """`format_message("Review {n}", n=pluralize(x, "broken link"))` hands
        gettext a msgid with no noun in it, so "broken link" cannot be
        translated at all. `format_plural` puts both wordings in the catalogue,
        which is what the POT generator already knows how to extract.

        `pluralize` is still right for report bodies and log lines, which never
        reach the catalogue. This only forbids nesting it inside a translator.
        """
        import ast

        root = Path(__file__).resolve().parents[1]
        translators = {"_", "format_message", "gettext", "ngettext"}
        offenders = []

        for source in sorted((root / "bookmark_organizer_pro").rglob("*.py")):
            text = source.read_text(encoding="utf-8")
            if "pluralize(" not in text:
                continue
            relative = source.relative_to(root).as_posix()
            for node in ast.walk(ast.parse(text, filename=relative)):
                if not isinstance(node, ast.Call):
                    continue
                name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
                if name not in translators:
                    continue
                for child in ast.walk(node):
                    if (
                        isinstance(child, ast.Call)
                        and getattr(child.func, "id", None) == "pluralize"
                    ):
                        offenders.append(f"{relative}:{node.lineno}")
                        break

        self.assertEqual(sorted(set(offenders)), [], "\n".join(sorted(set(offenders))))

    def test_product_strings_avoid_em_and_en_dashes(self):
        """The writing rule covers anything a person reads, which includes the
        strings the desktop, the CLI, and the dialogs render.

        Three uses stay, and none of them are prose: log lines, which the rule
        exempts along with comments and test names; a lone dash standing in for
        an empty table cell, which is a glyph for "no value"; and a numeric
        range written "{start}-{end}", which is the one job an en dash has.

        The exemptions are deliberately narrow. Matching a stripped value let
        " - ".join(...) through, and exempting everything under a log call let
        log.debug(self._set_status("...")) through with it, so a placeholder
        now has to be the entire string and only a log call's own direct
        arguments count as logged.
        """
        import ast

        root = Path(__file__).resolve().parents[1]
        dashes = ("\u2014", "\u2013")
        placeholders = {"\u2014", "\u2013"}
        offenders = []

        targets = sorted((root / "bookmark_organizer_pro").rglob("*.py"))
        targets += sorted((root / "scripts").rglob("*.py"))
        benchmarks = root / "benchmarks"
        if benchmarks.is_dir():
            targets += sorted(benchmarks.rglob("*.py"))
        targets.append(root / "main.py")

        def direct_string_args(call):
            """The strings this call itself passes, not everything beneath it."""
            for argument in list(call.args) + [kw.value for kw in call.keywords]:
                if isinstance(argument, ast.Constant):
                    yield argument
                elif isinstance(argument, ast.JoinedStr):
                    for piece in argument.values:
                        if isinstance(piece, ast.Constant):
                            yield piece

        for source in targets:
            text = source.read_text(encoding="utf-8")
            if not any(dash in text for dash in dashes):
                continue
            relative = source.relative_to(root).as_posix()
            tree = ast.parse(text, filename=relative)

            docstrings = set()
            logged = set()
            for node in ast.walk(tree):
                body = getattr(node, "body", None)
                if isinstance(
                    node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
                ) and body:
                    first = body[0]
                    if (
                        isinstance(first, ast.Expr)
                        and isinstance(first.value, ast.Constant)
                        and isinstance(first.value.value, str)
                    ):
                        docstrings.add(id(first.value))
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "log"
                    and node.func.attr in {"debug", "info", "warning", "error", "exception", "critical"}
                ):
                    for argument in direct_string_args(node):
                        logged.add(id(argument))

            for node in ast.walk(tree):
                if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                    continue
                value = node.value
                if not any(dash in value for dash in dashes):
                    continue
                if id(node) in docstrings or id(node) in logged:
                    continue
                if value in placeholders:
                    continue
                if any(f"}}{dash}{{" in value for dash in dashes):
                    continue
                if source.name == "ai_tools.py" and value.startswith(r"\s*[|"):
                    continue
                offenders.append(f"{relative}:{node.lineno}: {value.strip()[:90]}")

        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_shipping_docs_avoid_em_and_en_dashes(self):
        """README and the changelog are both read by users, and the newest
        changelog section is reused verbatim as release notes, so the whole of
        both files follows the project's writing rule. R-144 backfilled the
        older changelog sections, so this now covers each file end to end
        instead of only the section at the top."""
        root = Path(__file__).resolve().parents[1]
        offenders = []

        for name in ("README.md", "CHANGELOG.md"):
            text = (root / name).read_text(encoding="utf-8")
            for number, line in enumerate(text.splitlines(), 1):
                if "—" in line or "–" in line:
                    offenders.append(f"{name}:{number}: {line.strip()[:90]}")

        self.assertEqual(offenders, [], "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
