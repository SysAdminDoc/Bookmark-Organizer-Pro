from pathlib import Path

from PIL import Image

from scripts import visual_regression_smoke as smoke


def test_visual_smoke_surface_matrix_covers_required_desktop_and_extension_views():
    assert {
        "desktop-main-empty-dark",
        "desktop-main-list-light",
        "desktop-assistant-settings",
        "desktop-import-progress",
        "desktop-export-dialog",
        "desktop-reader-view",
        "desktop-graph-view",
    } <= set(smoke.DESKTOP_SURFACES)

    extension_names = {surface.name for surface in smoke.EXTENSION_SURFACES}
    assert {
        "extension-popup-dark",
        "extension-popup-light",
        "extension-options-light",
        "extension-sidepanel-recent-dark",
        "extension-sidepanel-add-light",
    } <= extension_names


def test_visual_smoke_rejects_blank_images(tmp_path: Path):
    blank = tmp_path / "blank.png"
    Image.new("RGB", (320, 240), "#111111").save(blank)

    try:
        smoke.assert_image_healthy(blank)
    except smoke.VisualSmokeError as exc:
        assert "blank" in str(exc)
    else:
        raise AssertionError("blank screenshot should fail visual smoke")
