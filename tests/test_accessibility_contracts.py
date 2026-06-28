from pathlib import Path

from scripts import accessibility_contract_smoke as a11y


ROOT = Path(__file__).resolve().parents[1]


def test_extension_accessibility_contracts_cover_all_extension_pages():
    report = a11y.run_checks()

    checked = {entry["file"] for entry in report["extension"]}
    assert checked == {"popup.html", "options.html", "sidepanel.html"}
    assert report["tk"]["focusable_label"] is True
    assert report["tk"]["modern_button"] is True


def test_accessibility_contract_rejects_unlabelled_controls(tmp_path: Path):
    page = tmp_path / "bad.html"
    page.write_text(
        """<!doctype html>
<html lang="en">
<head><title>Bad</title></head>
<body><main><input id="missing"></main></body>
</html>
""",
        encoding="utf-8",
    )

    try:
        a11y.check_extension_file(page)
    except a11y.AccessibilityContractError as exc:
        assert "accessible name" in str(exc)
    else:
        raise AssertionError("unlabelled control should fail accessibility contract")
