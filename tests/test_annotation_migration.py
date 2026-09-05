from __future__ import annotations

import csv
import hashlib
import io
import json
import tracemalloc
from pathlib import Path
from unittest import mock

import pytest

from bookmark_organizer_pro.services import migration

from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.migration import apply_migration, preflight_migration
from bookmark_organizer_pro.services.reader_annotations import (
    ANNOTATION_EXPORT_SCHEMA,
    AnnotationExportTemplate,
    DEFAULT_ANNOTATION_FIELDS,
    LEGACY_ANNOTATION_EXPORT_SCHEMA,
    ReaderAnnotationStore,
    ReaderHighlight,
    annotation_export_records,
    export_annotations,
    parse_annotation_export,
    reconcile_highlight_anchor,
    render_annotation_export,
    source_text_sha256,
)


def _bookmark(bookmark_id: int = 7) -> Bookmark:
    return Bookmark(
        id=bookmark_id, url="https://example.com/paper", title="A Paper",
        category="Papers", parent_category="Research", tags=["python", "retrieval"],
        notes="Document note", created_at="2026-01-01T00:00:00+00:00",
        modified_at="2026-01-02T00:00:00+00:00",
    )


def _highlight(highlight_id: str, modified: str, text: str = "Evidence") -> ReaderHighlight:
    return ReaderHighlight(
        id=highlight_id, bookmark_id=7, char_start=4, char_end=12, text=text,
        color="green", note="Important", tags=["claim"],
        created_at="2026-01-03T00:00:00+00:00", modified_at=modified,
        sr_interval=6, sr_repetitions=2, sr_ease=2.6, sr_next_review="2026-02-01",
    )


def test_annotation_export_is_deterministic_and_incremental():
    older = _highlight("older", "2026-02-01T00:00:00+00:00", "Old")
    newer = _highlight("newer", "2026-03-01T00:00:00+00:00", "New")
    records = annotation_export_records(
        [_bookmark()], [newer, older], changed_since="2026-02-15T00:00:00Z"
    )
    assert [record["highlight_id"] for record in records] == ["newer"]
    assert records[0]["document_category"] == "Research / Papers"
    assert records[0]["highlight_tags"] == ["claim"]
    assert records[0]["review_repetitions"] == 2
    assert records[0]["source_link"].endswith("#bop-highlight-newer")
    template = AnnotationExportTemplate(format="json")
    assert render_annotation_export(records, template) == render_annotation_export(records, template)


def test_reader_anchor_creation_bounds_context_and_migrates_legacy_storage(tmp_path: Path):
    path = tmp_path / "reader-annotations.json"
    source = ("p" * 80) + "selected evidence" + ("s" * 80)
    start = source.index("selected evidence")
    store = ReaderAnnotationStore(path)

    created = store.add_from_text(7, source, start, start + len("selected evidence"))

    assert created.source_sha256 == source_text_sha256(source)
    assert created.quote_exact == "selected evidence"
    assert created.quote_prefix == "p" * 64
    assert created.quote_suffix == "s" * 64
    assert created.anchor_status == "anchored"
    unchanged = store.reconcile_for_bookmark(7, source)[0]
    assert (unchanged.char_start, unchanged.char_end) == (
        created.char_start,
        created.char_end,
    )
    assert unchanged.anchor_history == []
    envelope = json.loads(path.read_text(encoding="utf-8"))
    assert envelope["version"] == 2

    legacy_path = tmp_path / "legacy-reader-annotations.json"
    legacy_path.write_text(
        json.dumps(
            {
                "highlights": [
                    {
                        "id": "legacy",
                        "bookmark_id": 7,
                        "char_start": start,
                        "char_end": start + len("selected evidence"),
                        "text": "selected evidence",
                        "note": "Keep this",
                        "tags": ["claim"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    migrated = ReaderAnnotationStore(legacy_path)
    legacy = migrated.list_for_bookmark(7)[0]
    assert legacy.anchor_status == "unverified"
    assert legacy.quote_exact == "selected evidence"
    resolved = migrated.reconcile_for_bookmark(7, source)[0]
    assert resolved.anchor_status == "anchored"
    assert resolved.source_sha256 == source_text_sha256(source)
    assert resolved.note == "Keep this"
    assert resolved.tags == ["claim"]
    assert json.loads(legacy_path.read_text(encoding="utf-8"))["version"] == 2


def test_reader_anchor_reconciles_unique_change_and_preserves_metadata(tmp_path: Path):
    path = tmp_path / "reader-annotations.json"
    old_source = "Before unique quote after"
    quote = "unique quote"
    start = old_source.index(quote)
    store = ReaderAnnotationStore(path)
    original = ReaderHighlight(
        id="stable-id",
        bookmark_id=7,
        char_start=start,
        char_end=start + len(quote),
        text=quote,
        source_sha256=source_text_sha256(old_source),
        quote_exact=quote,
        quote_prefix="Before ",
        quote_suffix=" after",
        anchor_status="anchored",
        note="Research note",
        tags=["claim", "review"],
        created_at="2026-01-03T00:00:00+00:00",
        modified_at="2026-01-03T00:00:00+00:00",
        sr_interval=6,
        sr_repetitions=2,
        sr_ease=2.6,
        sr_next_review="2026-02-01",
    )
    assert store.restore(original)
    changed_source = "Inserted context. Before unique quote after"

    resolved = store.reconcile_for_bookmark(7, changed_source)[0]

    assert resolved.id == original.id
    assert changed_source[resolved.char_start:resolved.char_end] == quote
    assert resolved.anchor_status == "reanchored"
    assert resolved.note == original.note
    assert resolved.tags == original.tags
    assert resolved.sr_interval == original.sr_interval
    assert resolved.sr_repetitions == original.sr_repetitions
    assert resolved.sr_next_review == original.sr_next_review
    assert resolved.anchor_history[-1]["action"] == "automatic-reanchor"


def test_reader_anchor_orphans_ambiguous_or_missing_quotes_and_manual_relink_preserves_data(
    tmp_path: Path,
):
    old_source = "A quote Z"
    original = ReaderHighlight(
        id="repair-me",
        bookmark_id=7,
        char_start=2,
        char_end=7,
        text="quote",
        source_sha256=source_text_sha256(old_source),
        quote_exact="quote",
        anchor_status="anchored",
        note="Do not lose",
        tags=["source"],
        created_at="2026-01-03T00:00:00+00:00",
        modified_at="2026-01-03T00:00:00+00:00",
        sr_interval=6,
        sr_repetitions=2,
        sr_next_review="2026-02-01",
    )
    ambiguous, changed = reconcile_highlight_anchor(
        original,
        "quote appears twice; quote",
    )
    assert changed
    assert ambiguous.anchor_status == "orphaned"
    assert ambiguous.orphan_reason == "exact quote has multiple possible matches"

    missing, changed = reconcile_highlight_anchor(original, "the passage is gone")
    assert changed
    assert missing.anchor_status == "orphaned"
    assert missing.orphan_reason == "exact quote was not found in the current source"

    store = ReaderAnnotationStore(tmp_path / "reader-annotations.json")
    assert store.restore(ambiguous)
    replacement_source = "A replacement passage now exists."
    replacement = "replacement passage"
    start = replacement_source.index(replacement)
    repaired = store.relink(
        original.id,
        replacement_source,
        start,
        start + len(replacement),
    )
    assert repaired is not None
    assert repaired.id == original.id
    assert repaired.text == replacement
    assert repaired.anchor_status == "reanchored"
    assert repaired.note == original.note
    assert repaired.tags == original.tags
    assert repaired.sr_interval == original.sr_interval
    assert repaired.sr_repetitions == original.sr_repetitions
    assert repaired.sr_next_review == original.sr_next_review
    assert [entry["action"] for entry in repaired.anchor_history][-2:] == [
        "orphaned",
        "manual-relink",
    ]


def test_annotation_v2_export_surfaces_orphans_and_accepts_v1_round_trip(tmp_path: Path):
    orphan = _highlight("orphan", "2026-03-01T00:00:00+00:00")
    orphan.anchor_status = "orphaned"
    orphan.orphan_reason = "exact quote was not found in the current source"
    output = tmp_path / "annotations.json"

    export_annotations([_bookmark()], [orphan], output, output_format="json")

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == ANNOTATION_EXPORT_SCHEMA
    assert payload["records"][0]["highlight_anchor_status"] == "orphaned"
    assert payload["records"][0]["highlight_orphan_reason"] == orphan.orphan_reason

    legacy = tmp_path / "legacy-annotations.json"
    legacy.write_text(
        json.dumps(
            {
                "schema": LEGACY_ANNOTATION_EXPORT_SCHEMA,
                "records": [{"highlight_id": "legacy"}],
            }
        ),
        encoding="utf-8",
    )
    assert parse_annotation_export(legacy) == [{"highlight_id": "legacy"}]


@pytest.mark.parametrize("output_format,suffix", [("json", ".json"), ("csv", ".csv")])
def test_annotation_custom_field_template_round_trips(tmp_path: Path, output_format: str, suffix: str):
    template_path = tmp_path / "template.json"
    template_path.write_text(json.dumps({
        "format": output_format,
        "fields": ["document_url", "highlight_text", "highlight_tags", "source_link"],
    }), encoding="utf-8")
    output = tmp_path / f"annotations{suffix}"
    export_annotations(
        [_bookmark()], [_highlight("h1", "2026-03-01T00:00:00+00:00")], output,
        template_path=template_path,
    )
    rows = parse_annotation_export(output)
    assert len(rows) == 1
    assert rows[0]["document_url"] == "https://example.com/paper"
    assert rows[0]["highlight_text"] == "Evidence"
    assert rows[0]["highlight_tags"] == (["claim"] if output_format == "json" else "claim")


@pytest.mark.parametrize("danger", ["=1+1", "+1", "-1", "@SUM", "\tx", "\rx", "|cmd"])
def test_annotation_csv_neutralizes_every_exported_cell(danger: str):
    list_fields = {"document_tags", "highlight_tags", "highlight_anchor_history"}
    record = {
        field: [danger] if field in list_fields else danger
        for field in DEFAULT_ANNOTATION_FIELDS
    }

    rendered = render_annotation_export(
        [record],
        AnnotationExportTemplate(format="csv"),
    )
    row = next(csv.DictReader(io.StringIO(rendered)))

    assert set(row) == set(DEFAULT_ANNOTATION_FIELDS)
    assert all(row[field] == f"'{danger}" for field in DEFAULT_ANNOTATION_FIELDS)


def test_annotation_csv_hardening_does_not_change_json_or_markdown():
    record = annotation_export_records(
        [_bookmark()],
        [_highlight("h1", "2026-03-01T00:00:00+00:00")],
    )[0]
    record["document_title"] = "=Document"
    record["highlight_text"] = "+Evidence"

    json_template = AnnotationExportTemplate(
        format="json",
        fields=("document_title", "highlight_text"),
    )
    assert render_annotation_export([record], json_template) == (
        json.dumps(
            {
                "schema": ANNOTATION_EXPORT_SCHEMA,
                "records": [
                    {
                        "document_title": "=Document",
                        "highlight_text": "+Evidence",
                    }
                ],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )

    markdown_template = AnnotationExportTemplate(
        format="markdown",
        document_header="{document_title}",
        highlight="{highlight_text}",
    )
    assert render_annotation_export([record], markdown_template) == "=Document\n\n+Evidence\n"


def test_markdown_template_uses_document_highlight_and_review_fields(tmp_path: Path):
    template_path = tmp_path / "template.json"
    template_path.write_text(json.dumps({
        "format": "markdown",
        "document_header": "# {document_title} [{document_category}]",
        "highlight": "{highlight_text} | {highlight_color} | {highlight_tags} | "
                     "{review_next} | {source_link}",
    }), encoding="utf-8")
    output = tmp_path / "annotations.md"
    export_annotations([_bookmark()], [_highlight("h1", "2026-03-01T00:00:00+00:00")], output,
                       template_path=template_path)
    rendered = output.read_text(encoding="utf-8")
    assert "# A Paper [Research / Papers]" in rendered
    assert "Evidence | green | claim | 2026-02-01" in rendered
    assert "#bop-highlight-h1" in rendered


def test_annotation_template_rejects_attribute_traversal(tmp_path: Path):
    template_path = tmp_path / "unsafe.json"
    template_path.write_text(json.dumps({
        "format": "markdown",
        "highlight": "{highlight_text.__class__}",
    }), encoding="utf-8")

    with pytest.raises(ValueError, match="unsafe"):
        AnnotationExportTemplate.load(template_path)


@pytest.mark.parametrize("value", ["{highlight_text!r}", "{highlight_text:>999999}"])
def test_annotation_template_rejects_conversions_and_format_specs(tmp_path: Path, value: str):
    template_path = tmp_path / "unsafe-format.json"
    template_path.write_text(
        json.dumps({"format": "markdown", "highlight": value}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="conversions and format specifications"):
        AnnotationExportTemplate.load(template_path)


@pytest.fixture
def migration_files(tmp_path: Path) -> dict[str, Path]:
    linkwarden = tmp_path / "linkwarden.json"
    linkwarden.write_text(json.dumps({"links": [{
        "id": "lw-1", "url": "https://one.example", "name": "One",
        "collection": {"name": "Papers", "parentName": "Research"},
        "tags": [{"name": "python"}], "description": "Note", "createdAt": "2026-01-01",
        "isArchived": True, "highlights": [{"text": "No offsets"}], "preview": "ignored",
    }]}), encoding="utf-8")
    karakeep = tmp_path / "karakeep.json"
    karakeep.write_text(json.dumps({"bookmarks": [{
        "id": "kh-1", "url": "https://two.example", "title": "Two",
        "lists": [{"name": "Inbox"}], "tags": ["saved"], "note": "Keep",
        "createdAt": "2026-01-02", "archived": False, "assets": ["not migrated"],
    }]}), encoding="utf-8")
    raindrop = tmp_path / "raindrop.csv"
    with raindrop.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["id", "url", "title", "folder", "tags", "note", "created", "cover"])
        writer.writeheader()
        writer.writerow({"id": "rd-1", "url": "https://three.example", "title": "Three",
                         "folder": "Work / Reading", "tags": "news, web", "note": "Later",
                         "created": "2026-01-03", "cover": "unsupported"})
    readwise = tmp_path / "readwise.csv"
    with readwise.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Document ID", "URL", "Title", "Category", "Tags",
                                                         "Document note", "Saved date", "Highlights"])
        writer.writeheader()
        writer.writerow({"Document ID": "rw-1", "URL": "https://four.example", "Title": "Four",
                         "Category": "Articles", "Tags": "read;research", "Document note": "Memo",
                         "Saved date": "2026-01-04", "Highlights": "Highlight without offsets"})
    return {"linkwarden": linkwarden, "karakeep": karakeep,
            "raindrop": raindrop, "readwise": readwise}


@pytest.mark.parametrize("source", ["linkwarden", "karakeep", "raindrop", "readwise"])
def test_competitor_preflight_reports_field_fidelity(source: str, migration_files: dict[str, Path]):
    plan = preflight_migration(source, migration_files[source])
    assert plan.report.source == source
    assert plan.report.total_records == plan.report.importable == 1
    assert plan.report.invalid == 0
    assert plan.report.preserved["url"] == 1
    assert plan.report.preserved["tags"] == 1
    assert plan.report.transformed["source_id_to_custom_data"] == 1
    assert len(plan.report.source_sha256) == 64
    bookmark = plan.bookmarks[0]
    assert bookmark.custom_data["migration"]["source"] == source
    assert bookmark.source_file == f"{source}-migration"


def test_preflight_counts_duplicates_invalid_and_unsupported(migration_files: dict[str, Path]):
    path = migration_files["linkwarden"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["links"].append({"url": "notaurl", "title": "Bad"})
    path.write_text(json.dumps(payload), encoding="utf-8")
    plan = preflight_migration("linkwarden", path, existing_urls=["https://one.example/"])
    assert plan.report.importable == 0
    assert plan.report.duplicates == 1
    assert plan.report.invalid == 1
    assert plan.report.unsupported["highlights_without_text_offsets"] == 1


class _FakeManager:
    def __init__(self):
        self.bookmarks: list[Bookmark] = []
        self.safepoints: list[str] = []
        self.saves = 0

    def get_all_bookmarks(self):
        return list(self.bookmarks)

    def create_safepoint(self, label):
        self.safepoints.append(label)
        return f"safepoints/{label}.json"

    def add_bookmark(self, bookmark, save=False):
        self.bookmarks.append(bookmark)

    def save_bookmarks(self):
        self.saves += 1


def test_apply_migration_is_safepointed_and_idempotent(migration_files: dict[str, Path]):
    manager = _FakeManager()
    first_plan = preflight_migration("raindrop", migration_files["raindrop"])
    first = apply_migration(manager, first_plan)
    second_plan = preflight_migration(
        "raindrop", migration_files["raindrop"],
        existing_urls=[bookmark.url for bookmark in manager.get_all_bookmarks()],
    )
    second = apply_migration(manager, second_plan)
    assert first.added == 1
    assert second.added == 0
    assert len(manager.bookmarks) == 1
    assert first.safepoint.startswith("safepoints/pre-raindrop-migration")
    assert manager.safepoints == ["pre-raindrop-migration", "pre-raindrop-migration"]


# ── R-154: the plan lives on disk, not in memory ─────────────────────────────


def test_the_spool_round_trip_preserves_every_converted_field(migration_files: dict[str, Path]):
    """Serializing through the spool must not quietly drop or coerce a field."""
    from bookmark_organizer_pro.services import migration as migration_module

    for source, path in migration_files.items():
        direct = []
        original_add = migration_module._PlanSpool.add

        def capture(self, canonical, payload, _original=original_add):
            direct.append(dict(payload))
            return _original(self, canonical, payload)

        with mock.patch.object(migration_module._PlanSpool, "add", capture):
            plan = preflight_migration(source, path)
        try:
            restored = [bookmark.to_dict() for bookmark in plan.iter_bookmarks()]
        finally:
            plan.close()
        assert restored == direct, f"{source} lost fields through the spool"


def test_the_plan_streams_without_materializing(migration_files: dict[str, Path]):
    plan = preflight_migration("linkwarden", migration_files["linkwarden"])
    try:
        streamed = plan.iter_bookmarks()
        assert not isinstance(streamed, (list, tuple))
        assert [bookmark.url for bookmark in streamed] == ["https://one.example"]
    finally:
        plan.close()


def test_existing_library_urls_dedupe_through_the_spool(migration_files: dict[str, Path]):
    plan = preflight_migration(
        "linkwarden", migration_files["linkwarden"], existing_urls=["https://one.example"]
    )
    try:
        assert plan.report.importable == 0
        assert plan.report.duplicates == 1
        assert list(plan.iter_bookmarks()) == []
    finally:
        plan.close()


def test_repeats_inside_one_export_collapse_to_one_record(tmp_path: Path):
    path = tmp_path / "repeats.json"
    path.write_text(
        json.dumps({"links": [
            {"url": "https://dupe.example/a", "name": "First"},
            {"url": "https://dupe.example/a", "name": "Second"},
            {"url": "https://other.example/b", "name": "Other"},
        ]}),
        encoding="utf-8",
    )

    plan = preflight_migration("linkwarden", path)
    try:
        assert plan.report.total_records == 3
        assert plan.report.importable == 2
        assert plan.report.duplicates == 1
        assert [bookmark.url for bookmark in plan.iter_bookmarks()] == [
            "https://dupe.example/a", "https://other.example/b"
        ]
    finally:
        plan.close()


def test_closing_a_plan_removes_its_spool_from_disk(migration_files: dict[str, Path]):
    plan = preflight_migration("linkwarden", migration_files["linkwarden"])
    spool_path = plan._spool.path
    assert spool_path.exists()

    plan.close()

    assert not spool_path.exists()
    assert not spool_path.parent.exists()
    plan.close()  # idempotent


def test_a_plan_used_as_a_context_manager_cleans_up(migration_files: dict[str, Path]):
    with preflight_migration("linkwarden", migration_files["linkwarden"]) as plan:
        spool_path = plan._spool.path
        assert spool_path.exists()

    assert not spool_path.exists()


def test_a_failing_preflight_leaves_no_spool_behind(migration_files: dict[str, Path], monkeypatch):
    from bookmark_organizer_pro.services import migration as migration_module

    created: list = []
    original_init = migration_module._PlanSpool.__init__

    def record(self, directory=None, _original=original_init):
        _original(self, directory)
        created.append(self)

    monkeypatch.setattr(migration_module._PlanSpool, "__init__", record)
    monkeypatch.setattr(
        migration_module, "_convert_item",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("conversion exploded")),
    )

    with pytest.raises(ValueError):
        preflight_migration("linkwarden", migration_files["linkwarden"])

    assert created, "the preflight never opened a spool"
    for spool in created:
        assert not spool.path.exists(), "a failed preflight left its spool on disk"


def test_a_discarded_plan_refuses_to_stream(migration_files: dict[str, Path]):
    plan = preflight_migration("linkwarden", migration_files["linkwarden"])
    plan.close()

    with pytest.raises(migration.MigrationSpoolError):
        list(plan.iter_bookmarks())


def test_an_oversized_export_is_refused_before_it_is_read(migration_files: dict[str, Path]):
    """The ceiling is checked against the file size, not after reading it."""
    limits = migration.MigrationLimits(max_source_bytes=8)

    with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("read anyway")):
        with pytest.raises(migration.MigrationSpoolError) as excinfo:
            preflight_migration("linkwarden", migration_files["linkwarden"], limits=limits)

    assert "max_source_bytes" in str(excinfo.value)


def test_the_cli_deletes_the_spool_on_a_dry_run(migration_files: dict[str, Path], capsys):
    """A preflight that the user never applies must leave no copy behind."""
    from bookmark_organizer_pro.cli import BookmarkCLI

    cli = BookmarkCLI.__new__(BookmarkCLI)
    cli.bookmark_manager = mock.Mock(get_all_bookmarks=lambda: [])
    namespace = mock.Mock(
        source="linkwarden",
        file=str(migration_files["linkwarden"]),
        report=None,
        action="preflight",
    )
    spools: list = []
    real_spool = migration._PlanSpool

    def capture(*args, **kwargs):
        spool = real_spool(*args, **kwargs)
        spools.append(spool)
        return spool

    with mock.patch.object(migration, "_PlanSpool", capture):
        assert cli._cmd_migration(namespace) == 0

    assert spools, "the preflight built no spool"
    assert not spools[0].path.exists()
    assert not spools[0].path.parent.exists()


def test_the_desktop_dialog_discards_the_spool_when_it_closes(migration_files: dict[str, Path]):
    """The review dialog owns the spool: destroying it deletes the copy."""
    source = (
        Path(__file__).resolve().parents[1]
        / "bookmark_organizer_pro" / "app_mixins" / "import_export.py"
    ).read_text(encoding="utf-8")

    assert 'dlg.bind("<Destroy>", discard_plan)' in source
    assert "plan.close()" in source


def _linkwarden_fixture(path: Path, *, target_bytes: int, filler_chars: int) -> int:
    filler = "x" * filler_chars
    written = 0
    index = 0
    with path.open("w", encoding="utf-8") as handle:
        handle.write('{"links": [')
        while written < target_bytes:
            record = json.dumps({
                "id": f"lw-{index}",
                "url": f"https://example.com/{index}",
                "name": f"Record {index}",
                "description": filler,
                "tags": [{"name": "alpha"}],
                "createdAt": "2026-01-01",
            })
            handle.write(("" if index == 0 else ",") + record)
            written += len(record) + 1
            index += 1
        handle.write("]}")
    return index


def _raindrop_fixture(path: Path, *, target_bytes: int, filler_chars: int) -> int:
    filler = "x" * filler_chars
    fields = ["id", "url", "title", "folder", "tags", "note", "created", "cover"]
    written = 0
    index = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        while written < target_bytes:
            writer.writerow({
                "id": f"rd-{index}", "url": f"https://example.org/{index}",
                "title": f"Title {index}", "folder": "Work", "tags": "news, web",
                "note": filler, "created": "2026-01-03", "cover": "",
            })
            written += filler_chars + 200
            index += 1
    return index


@pytest.mark.parametrize(
    "source,builder,name",
    [
        ("linkwarden", _linkwarden_fixture, "big.json"),
        ("raindrop", _raindrop_fixture, "big.csv"),
    ],
)
def test_a_250mb_export_streams_without_becoming_resident(source, builder, name, tmp_path: Path):
    """The whole point of the spool: the source is never held in memory."""
    path = tmp_path / name
    expected_records = builder(path, target_bytes=250 * 1024 * 1024, filler_chars=9000)
    assert path.stat().st_size > 240 * 1024 * 1024

    tracemalloc.start()
    try:
        plan = preflight_migration(source, path)
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    with plan:
        assert peak < 96 * 1024 * 1024, f"peak allocation was {peak / 1024 / 1024:.1f} MiB"
        assert plan.report.total_records == expected_records
        # One pass over the bytes still produces the digest of the whole file.
        assert plan.report.source_sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


def test_the_source_is_opened_once(migration_files: dict[str, Path]):
    """Hashing used to read the file, then parsing read it again."""
    opens = []
    real_open = Path.open

    def counting_open(self, *args, **kwargs):
        opens.append(str(self))
        return real_open(self, *args, **kwargs)

    with mock.patch.object(Path, "open", counting_open):
        plan = preflight_migration("linkwarden", migration_files["linkwarden"])

    with plan:
        assert opens.count(str(migration_files["linkwarden"])) == 1


@pytest.mark.parametrize(
    "limits,fixture_kwargs,expected",
    [
        (migration.MigrationLimits(max_records=2), {}, "max_records"),
        (
            migration.MigrationLimits(max_field_chars=64),
            {"filler_chars": 500},
            "max_field_chars",
        ),
    ],
)
def test_a_ceiling_refuses_the_export_and_names_itself(
    limits, fixture_kwargs, expected, tmp_path: Path
):
    path = tmp_path / "big.json"
    _linkwarden_fixture(
        path,
        target_bytes=fixture_kwargs.get("target_bytes", 4096),
        filler_chars=fixture_kwargs.get("filler_chars", 10),
    )

    with pytest.raises(migration.MigrationSpoolError) as excinfo:
        preflight_migration("linkwarden", path, limits=limits)

    assert expected in str(excinfo.value)


def test_a_deeply_nested_record_is_refused_by_name(tmp_path: Path):
    payload = {"url": "https://deep.example", "name": "Deep"}
    nested: dict = {}
    payload["custom"] = nested
    for _level in range(12):
        child: dict = {}
        nested["child"] = child
        nested = child
    path = tmp_path / "deep.json"
    path.write_text(json.dumps({"links": [payload]}), encoding="utf-8")

    with pytest.raises(migration.MigrationSpoolError) as excinfo:
        preflight_migration(
            "linkwarden", path, limits=migration.MigrationLimits(max_json_depth=4)
        )

    assert "max_json_depth" in str(excinfo.value)


def test_a_refused_ceiling_leaves_no_spool_behind(tmp_path: Path):
    path = tmp_path / "big.json"
    _linkwarden_fixture(path, target_bytes=4096, filler_chars=10)
    spools: list = []
    real_spool = migration._PlanSpool

    def capture(*args, **kwargs):
        spool = real_spool(*args, **kwargs)
        spools.append(spool)
        return spool

    with mock.patch.object(migration, "_PlanSpool", capture):
        with pytest.raises(migration.MigrationSpoolError):
            preflight_migration(
                "linkwarden", path, limits=migration.MigrationLimits(max_records=2)
            )

    assert spools and not spools[0].path.parent.exists()


def test_a_json_export_with_no_bookmark_array_is_rejected(tmp_path: Path):
    path = tmp_path / "wrong.json"
    path.write_text(json.dumps({"unrelated": {"nothing": 1}}), encoding="utf-8")

    with pytest.raises(ValueError, match="supported bookmark list"):
        preflight_migration("linkwarden", path)


def test_a_top_level_json_array_still_parses(tmp_path: Path):
    path = tmp_path / "bare.json"
    path.write_text(
        json.dumps([{"url": "https://bare.example", "name": "Bare"}]), encoding="utf-8"
    )

    with preflight_migration("linkwarden", path) as plan:
        assert plan.report.total_records == 1
        assert plan.bookmarks[0].url == "https://bare.example"
