import subprocess
import sys
import json
import hashlib
from pathlib import Path

from scripts import release_artifact_smoke as smoke
from bookmark_organizer_pro import release_contract


def _artifact(tmp_path: Path) -> Path:
    path = tmp_path / ("BookmarkOrganizerPro.exe" if sys.platform.startswith("win") else "BookmarkOrganizerPro")
    path.write_bytes(b"0" * 1_000_001)
    return path


def _contract(version: str = "6.11.0", *, dirty: bool = False) -> dict:
    return {
        "ok": True,
        "app_version": version,
        "commit": "a" * 40,
        "dirty": dirty,
        "release_profile": "all",
        "sbom_components": 119,
        "errors": [],
        "capabilities": {
            "default_categories": {"available": True, "categories": 48, "patterns": 7550},
        },
    }


def test_release_artifact_smoke_accepts_expected_version(tmp_path: Path):
    artifact = _artifact(tmp_path)

    def runner(*args, **kwargs):
        command = args[0]
        stdout = json.dumps(_contract()) if "--release-contract" in command else "Bookmark Organizer Pro v6.11.0\n"
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    result = smoke.smoke_artifact(artifact, expected_version="6.11.0", runner=runner)

    assert result.returncode == 0
    assert result.stdout == "Bookmark Organizer Pro v6.11.0"
    assert result.contract["sbom_components"] == 119


def test_release_artifact_smoke_rejects_wrong_version(tmp_path: Path):
    artifact = _artifact(tmp_path)

    def runner(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, stdout="Bookmark Organizer Pro v0.0.0\n", stderr="")

    try:
        smoke.smoke_artifact(artifact, expected_version="6.11.0", runner=runner)
    except smoke.ReleaseArtifactSmokeError as exc:
        assert "unexpected version" in str(exc)
    else:
        raise AssertionError("wrong artifact version should fail smoke")


def test_release_artifact_smoke_rejects_failed_runtime_contract(tmp_path: Path):
    artifact = _artifact(tmp_path)

    def runner(*args, **kwargs):
        command = args[0]
        if "--release-contract" in command:
            contract = _contract()
            contract["ok"] = False
            contract["errors"] = ["capability firefox_jsonlz4 failed"]
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(contract), stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="Bookmark Organizer Pro v6.11.0\n", stderr="")

    try:
        smoke.smoke_artifact(artifact, expected_version="6.11.0", runner=runner)
    except smoke.ReleaseArtifactSmokeError as exc:
        assert "firefox_jsonlz4" in str(exc)
    else:
        raise AssertionError("failed runtime capability contract should fail smoke")


def test_release_artifact_smoke_rejects_missing_or_tiny_artifact(tmp_path: Path):
    try:
        smoke.check_artifact_file(tmp_path / "missing.exe")
    except smoke.ReleaseArtifactSmokeError as exc:
        assert "does not exist" in str(exc)
    else:
        raise AssertionError("missing artifact should fail smoke")

    tiny = tmp_path / "tiny.exe"
    tiny.write_bytes(b"small")
    try:
        smoke.check_artifact_file(tiny)
    except smoke.ReleaseArtifactSmokeError as exc:
        assert "unexpectedly small" in str(exc)
    else:
        raise AssertionError("tiny artifact should fail smoke")


def test_runtime_contract_validates_embedded_categories_lock_and_sbom(tmp_path: Path):
    lock = b'lock-version = "1.0"\n'
    (tmp_path / "pylock.toml").write_bytes(lock)
    (tmp_path / "release_manifest.json").write_text(json.dumps({
        "schema_version": 2,
        "runtime_capabilities": [{
            "name": "default_categories",
            "module": "bookmark_organizer_pro.core.default_categories",
            "minimum_categories": 48,
            "minimum_patterns": 7500,
        }],
    }), encoding="utf-8")
    (tmp_path / "build_identity.json").write_text(json.dumps({
        "schema_version": 1,
        "app_version": release_contract.APP_VERSION,
        "commit": "b" * 40,
        "dirty": False,
        "release_profile": "all",
        "lock_sha256": hashlib.sha256(lock).hexdigest(),
        "lock_verified": True,
        "dependency_versions": {},
    }), encoding="utf-8")
    (tmp_path / "sbom.cdx.json").write_text(json.dumps({
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "components": [],
    }), encoding="utf-8")

    report = release_contract.build_runtime_contract(tmp_path)

    assert report["ok"] is True
    assert report["capabilities"]["default_categories"]["categories"] == 48
    assert report["capabilities"]["default_categories"]["patterns"] >= 7500
