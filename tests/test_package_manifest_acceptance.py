"""Release-lock manifest integrity contract."""

from __future__ import annotations

import json

import pytest

from scripts import package_contract_audit as audit


def test_release_manifest_binds_verified_target_to_exact_lock_bytes(tmp_path, monkeypatch):
    lock = tmp_path / "pylock.toml"
    lock.write_bytes(audit.LOCK.read_bytes())
    manifest_data = json.loads(audit.RELEASE_MANIFEST.read_text(encoding="utf-8"))
    manifest_data["locks"][0]["path"] = str(lock)
    manifest_data["locks"][0]["sha256"] = "0" * 64
    manifest = tmp_path / "release_manifest.json"
    manifest.write_text(json.dumps(manifest_data), encoding="utf-8")
    monkeypatch.setattr(audit, "RELEASE_MANIFEST", manifest)

    with pytest.raises(audit.ContractError, match="digest drift"):
        audit.validate_dependency_contract()
