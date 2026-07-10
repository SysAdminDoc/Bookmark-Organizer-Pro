import subprocess
import sys
from pathlib import Path

from scripts import release_artifact_smoke as smoke


def _artifact(tmp_path: Path) -> Path:
    path = tmp_path / ("BookmarkOrganizerPro.exe" if sys.platform.startswith("win") else "BookmarkOrganizerPro")
    path.write_bytes(b"0" * 1_000_001)
    return path


def test_release_artifact_smoke_accepts_expected_version(tmp_path: Path):
    artifact = _artifact(tmp_path)

    def runner(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, stdout="Bookmark Organizer Pro v6.10.0\n", stderr="")

    result = smoke.smoke_artifact(artifact, expected_version="6.10.0", runner=runner)

    assert result.returncode == 0
    assert result.stdout == "Bookmark Organizer Pro v6.10.0"


def test_release_artifact_smoke_rejects_wrong_version(tmp_path: Path):
    artifact = _artifact(tmp_path)

    def runner(*args, **kwargs):
        return subprocess.CompletedProcess(args[0], 0, stdout="Bookmark Organizer Pro v0.0.0\n", stderr="")

    try:
        smoke.smoke_artifact(artifact, expected_version="6.10.0", runner=runner)
    except smoke.ReleaseArtifactSmokeError as exc:
        assert "unexpected version" in str(exc)
    else:
        raise AssertionError("wrong artifact version should fail smoke")


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
