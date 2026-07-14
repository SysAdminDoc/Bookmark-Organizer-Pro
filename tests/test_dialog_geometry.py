"""Dialog geometry and keyboard-accessibility contracts."""

from pathlib import Path
import threading
from types import SimpleNamespace

from bookmark_organizer_pro.ui.dependencies import DependencyCheckDialog
from bookmark_organizer_pro.ui.reader_view import ReaderViewDialog
from bookmark_organizer_pro.ui.window_geometry import fit_window_geometry
from bookmark_organizer_pro.utils.dependencies import DependencyInstallReport
from bookmark_organizer_pro.services.reader_annotations import ReaderAnnotationStore


ROOT = Path(__file__).resolve().parents[1]


def test_dialog_geometry_fits_supported_laptop_viewport():
    geometry = fit_window_geometry(640, 760, 1280, 720)
    assert geometry.width == 640
    assert geometry.height <= 672
    assert geometry.x >= 24
    assert geometry.y >= 24
    assert geometry.x + geometry.width <= 1280 - 24
    assert geometry.y + geometry.height <= 720 - 24


def test_mouse_only_labels_use_shared_keyboard_activation():
    shell = (ROOT / "bookmark_organizer_pro/app_mixins/app_shell.py").read_text(
        encoding="utf-8"
    )
    editor = (ROOT / "bookmark_organizer_pro/ui/widget_bookmark_editor.py").read_text(
        encoding="utf-8"
    )
    assert "make_keyboard_activatable(self._nl_toggle_btn" in shell
    assert "make_keyboard_activatable(add_btn, add_ai_tags)" in editor


def test_bookmark_editor_uses_scrollable_body_and_fixed_footer():
    source = (ROOT / "bookmark_organizer_pro/ui/widget_bookmark_editor.py").read_text(
        encoding="utf-8"
    )
    assert "self.content_canvas" in source
    assert 'self.bind("<Prior>"' in source
    assert 'self.bind("<Next>"' in source
    assert "btn_frame = tk.Frame(self" in source


def test_dependency_dialog_waits_for_real_installer_cancellation():
    source = (ROOT / "bookmark_organizer_pro/ui/dependencies.py").read_text(encoding="utf-8")
    manager_source = (ROOT / "bookmark_organizer_pro/utils/dependencies.py").read_text(encoding="utf-8")

    assert 'text=_("Cancelling installer safely...")' in source
    assert "self.dep_manager.cancel_installation()" in source
    assert "DependencyInstallReport" in source
    assert "self._post_ui" in source
    assert "subprocess.Popen" in manager_source
    assert "process.terminate()" in manager_source
    assert "process.kill()" in manager_source


class _Control:
    def __init__(self):
        self.state = "normal"
        self.text = ""
        self.config = {}
        self.focused = False

    def set_state(self, state):
        self.state = state

    def set_text(self, text):
        self.text = text

    def configure(self, **kwargs):
        self.config.update(kwargs)

    def stop(self):
        self.state = "stopped"

    def pack_forget(self):
        self.state = "hidden"

    def focus_set(self):
        self.focused = True

    def delete(self, *_args):
        self.text = ""


class _ListControl:
    def __init__(self):
        self.selected = None
        self.focused = False

    def selection_clear(self, *_args):
        self.selected = None

    def selection_set(self, index):
        self.selected = index

    def activate(self, index):
        self.selected = index

    def see(self, index):
        self.selected = index

    def focus_set(self):
        self.focused = True


def test_dependency_dialog_cancel_stays_visible_until_worker_finishes():
    cancelled = threading.Event()
    dialog = object.__new__(DependencyCheckDialog)
    dialog.result = True
    dialog._installing = True
    dialog._cancel_requested = False
    dialog.progress_label = _Control()
    dialog.cancel_btn = _Control()
    dialog._theme = SimpleNamespace(accent_warning="warning")
    dialog.dep_manager = SimpleNamespace(cancel_installation=lambda: cancelled.set())
    dialog._post_ui = lambda callback: callback()
    destroyed = []
    dialog.destroy = lambda: destroyed.append(True)

    dialog._on_cancel()

    assert cancelled.wait(timeout=2)
    assert destroyed == []
    assert dialog.result is False
    assert dialog._cancel_requested is True
    assert dialog.progress_label.config["text"] == "Cancelling installer safely..."


def test_dependency_dialog_reports_completed_mutations_after_cancel():
    dialog = object.__new__(DependencyCheckDialog)
    dialog._installing = True
    dialog.progress_bar = _Control()
    dialog.progress_label = _Control()
    dialog.cancel_btn = _Control()
    dialog.install_btn = _Control()
    dialog.skip_btn = _Control()
    dialog._theme = SimpleNamespace(accent_warning="warning", accent_success="success", accent_error="error")
    report = DependencyInstallReport(
        success=False,
        cancelled=True,
        installed=("Pillow",),
        skipped=("requests",),
    )

    dialog._installation_complete(False, report)

    assert dialog._installing is False
    assert "Installed before cancellation: Pillow" in dialog.progress_label.config["text"]
    assert dialog.cancel_btn.text == "Close"
    assert dialog.install_btn.text == "Retry Remaining"
    assert dialog.install_btn.state == "normal"


def test_reader_delete_exposes_focusable_one_step_undo(tmp_path):
    store = ReaderAnnotationStore(tmp_path / "reader-annotations.json")
    highlight = store.add_from_text(
        9,
        "Alpha selected passage omega",
        6,
        22,
        color="blue",
        note="Keep this note",
    )
    dialog = object.__new__(ReaderViewDialog)
    dialog.store = store
    dialog._deleted_highlight = None
    dialog.highlight_ids = [highlight.id]
    dialog._selected_highlight_id = lambda: highlight.id
    dialog.note_text = _Control()
    dialog.status = _Control()
    dialog.undo_delete_button = _Control()
    dialog.highlight_list = _ListControl()
    dialog._load_highlights = lambda: setattr(
        dialog,
        "highlight_ids",
        [item.id for item in store.list_for_bookmark(9)],
    )
    dialog._on_highlight_selected = lambda: None

    dialog._delete_selected_highlight()

    assert store.get(highlight.id) is None
    assert dialog._deleted_highlight.to_dict() == highlight.to_dict()
    assert dialog.undo_delete_button.state == "normal"
    assert dialog.undo_delete_button.focused is True
    assert "Undo" in dialog.status.config["text"]

    assert dialog._undo_deleted_highlight() == "break"
    assert store.get(highlight.id).to_dict() == highlight.to_dict()
    assert dialog._deleted_highlight is None
    assert dialog.undo_delete_button.state == "disabled"
    assert dialog.highlight_list.selected == 0
    assert dialog.highlight_list.focused is True


def test_reader_undo_keyboard_contract_is_bound_to_session_action():
    source = (ROOT / "bookmark_organizer_pro/ui/reader_view.py").read_text(encoding="utf-8")
    assert 'self.bind("<Control-z>", self._undo_deleted_highlight)' in source
    assert 'self.bind("<Command-z>", self._undo_deleted_highlight)' in source
    assert 'text=_("Undo")' in source
    assert 'state="disabled"' in source
