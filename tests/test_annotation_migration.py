from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.migration import apply_migration, preflight_migration
from bookmark_organizer_pro.services.reader_annotations import (
    AnnotationExportTemplate,
    ReaderHighlight,
    annotation_export_records,
    export_annotations,
    parse_annotation_export,
    render_annotation_export,
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
