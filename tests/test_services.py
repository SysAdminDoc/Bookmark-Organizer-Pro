"""Unit tests for the service layer.

Exercises EmbeddingService, EncryptedStore, TagLinter, FlowManager,
DailyDigestService, RSS feed parsing / FeedRegistry, ZipExporter,
and ReadLaterQueue using isolated temp directories.
"""

import importlib
import json
import os
import shutil
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch


def _make_bookmark(**overrides):
    """Helper — create a Bookmark with sensible defaults."""
    from bookmark_organizer_pro.models import Bookmark

    defaults = dict(
        id=None,
        url="https://example.com",
        title="Example",
    )
    defaults.update(overrides)
    return Bookmark(**defaults)


class _IsolatedTestBase(unittest.TestCase):
    """Redirect BOOKMARK_DATA_DIR to a temp dir, reload constants."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp(prefix="bop_svc_test_")
        os.environ["BOOKMARK_DATA_DIR"] = cls._tmp

        import bookmark_organizer_pro.constants as _c
        importlib.reload(_c)
        _c.ensure_directories()

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("BOOKMARK_DATA_DIR", None)
        shutil.rmtree(cls._tmp, ignore_errors=True)


# ── 0. Update policy ─────────────────────────────────────────────────

class TestUpdateManager(_IsolatedTestBase):
    """Tests for disabled-by-default update policy."""

    def _updates_module(self):
        import bookmark_organizer_pro.services.updates as updates
        return importlib.reload(updates)

    def setUp(self):
        updates = self._updates_module()
        if updates.UPDATE_CONFIG_FILE.exists():
            updates.UPDATE_CONFIG_FILE.unlink()
        shutil.rmtree(updates.UPDATE_CACHE_DIR, ignore_errors=True)

    def test_default_status_is_disabled(self):
        updates = self._updates_module()
        manager = updates.UpdateManager()

        status = manager.status()

        self.assertFalse(status.policy.enabled)
        self.assertFalse(status.policy.configured)
        self.assertFalse(status.can_check)
        self.assertEqual(status.reason, "disabled")

    def test_configure_requires_https_repository_urls(self):
        updates = self._updates_module()
        manager = updates.UpdateManager()

        with self.assertRaises(ValueError):
            manager.configure(metadata_url="http://updates.example.com/metadata")

        policy = manager.configure(
            enabled=True,
            metadata_url="https://updates.example.com/metadata/",
            targets_url="https://updates.example.com/targets/",
            channel="stable",
        )

        self.assertTrue(policy.enabled)
        self.assertEqual(policy.metadata_url, "https://updates.example.com/metadata")
        self.assertEqual(policy.targets_url, "https://updates.example.com/targets")
        self.assertTrue(policy.configured)

    def test_status_ready_when_enabled_configured_and_tufup_available(self):
        updates = self._updates_module()
        manager = updates.UpdateManager()
        manager.configure(
            enabled=True,
            metadata_url="https://updates.example.com/metadata",
            targets_url="https://updates.example.com/targets",
        )
        manager.metadata_dir.mkdir(parents=True, exist_ok=True)
        manager.trusted_root_path.write_text("{}", encoding="utf-8")

        with patch.object(updates, "tufup_available", return_value=True):
            status = manager.status()

        self.assertTrue(status.can_check)
        self.assertEqual(status.reason, "ready")

    def test_status_requires_trusted_root_metadata(self):
        updates = self._updates_module()
        manager = updates.UpdateManager()
        manager.configure(
            enabled=True,
            metadata_url="https://updates.example.com/metadata",
            targets_url="https://updates.example.com/targets",
        )

        with patch.object(updates, "tufup_available", return_value=True):
            status = manager.status()

        self.assertFalse(status.can_check)
        self.assertEqual(status.reason, "trusted root metadata missing")

    def test_check_for_updates_uses_client_without_downloading(self):
        updates = self._updates_module()
        manager = updates.UpdateManager(current_version="6.6.27")
        manager.configure(
            enabled=True,
            metadata_url="https://updates.example.com/metadata",
            targets_url="https://updates.example.com/targets",
        )
        manager.metadata_dir.mkdir(parents=True, exist_ok=True)
        manager.trusted_root_path.write_text("{}", encoding="utf-8")

        class FakeTarget:
            version = "6.7.0"
            filename = "BookmarkOrganizerPro-6.7.0.tar.gz"
            target_path_str = "BookmarkOrganizerPro-6.7.0.tar.gz"

        class FakeClient:
            created_with = None
            checked_with = None

            def __init__(self, **kwargs):
                FakeClient.created_with = kwargs

            def check_for_updates(self, **kwargs):
                FakeClient.checked_with = kwargs
                return FakeTarget()

        with patch.object(updates, "tufup_available", return_value=True):
            result = manager.check_for_updates(client_cls=FakeClient)

        self.assertTrue(result.checked)
        self.assertTrue(result.update_available)
        self.assertEqual(result.latest_version, "6.7.0")
        self.assertEqual(FakeClient.created_with["metadata_dir"], manager.metadata_dir)
        self.assertEqual(FakeClient.created_with["target_dir"], manager.target_dir)
        self.assertEqual(FakeClient.checked_with, {"pre": None, "patch": True})

    def test_download_update_stages_target_without_applying(self):
        updates = self._updates_module()
        manager = updates.UpdateManager(current_version="6.6.27")
        manager.configure(
            enabled=True,
            metadata_url="https://updates.example.com/metadata",
            targets_url="https://updates.example.com/targets",
        )
        manager.metadata_dir.mkdir(parents=True, exist_ok=True)
        manager.trusted_root_path.write_text("{}", encoding="utf-8")

        class FakeTarget:
            version = "6.7.0"
            filename = "BookmarkOrganizerPro-6.7.0.tar.gz"
            target_path_str = "BookmarkOrganizerPro-6.7.0.tar.gz"

        class FakeTargetInfo:
            path = "BookmarkOrganizerPro-6.7.0.tar.gz"

        class FakeClient:
            downloaded_with = None
            apply_called = False

            def __init__(self, **kwargs):
                self.new_targets = {}

            def check_for_updates(self, **kwargs):
                self.new_targets = {FakeTarget(): FakeTargetInfo()}
                return FakeTarget()

            def download_target(self, targetinfo, filepath=None, target_base_url=None):
                FakeClient.downloaded_with = (targetinfo, filepath, target_base_url)
                staged = manager.target_dir / targetinfo.path
                staged.parent.mkdir(parents=True, exist_ok=True)
                staged.write_bytes(b"archive")
                return str(staged)

            def download_and_apply_update(self, *args, **kwargs):
                FakeClient.apply_called = True
                raise AssertionError("apply should not be called")

        with patch.object(updates, "tufup_available", return_value=True):
            result = manager.download_update(client_cls=FakeClient)

        self.assertTrue(result.checked)
        self.assertTrue(result.update_available)
        self.assertTrue(result.downloaded)
        self.assertEqual(result.reason, "download staged")
        self.assertEqual(result.latest_version, "6.7.0")
        self.assertEqual(len(result.staged_paths), 1)
        self.assertTrue(Path(result.staged_paths[0]).exists())
        self.assertEqual(FakeClient.downloaded_with[2], "https://updates.example.com/targets")
        self.assertFalse(FakeClient.apply_called)

        manifest = json.loads(manager.staged_manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["latest_version"], "6.7.0")
        self.assertEqual(manifest["staged_paths"], list(result.staged_paths))

        staged = manager.staged_update()
        self.assertTrue(staged.available)
        self.assertTrue(staged.complete)
        self.assertEqual(staged.latest_version, "6.7.0")
        self.assertEqual(staged.reason, "staged target files present")

    def test_staged_update_status_reports_missing_targets(self):
        updates = self._updates_module()
        manager = updates.UpdateManager(current_version="6.6.27")
        manager.target_dir.mkdir(parents=True, exist_ok=True)
        missing = manager.target_dir / "BookmarkOrganizerPro-6.7.0.tar.gz"
        manager.staged_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manager.staged_manifest_path.write_text(json.dumps({
            "current_version": "6.6.27",
            "latest_version": "6.7.0",
            "target_name": "BookmarkOrganizerPro-6.7.0.tar.gz",
            "target_path": "BookmarkOrganizerPro-6.7.0.tar.gz",
            "staged_paths": [str(missing)],
            "channel": "stable",
            "staged_at": "2026-06-06T00:00:00+00:00",
        }), encoding="utf-8")

        staged = manager.staged_update()

        self.assertTrue(staged.available)
        self.assertFalse(staged.complete)
        self.assertEqual(staged.reason, "staged target files missing")

    def test_apply_preflight_reports_no_staged_update(self):
        updates = self._updates_module()
        manager = updates.UpdateManager(current_version="6.6.27")

        result = manager.apply_preflight()

        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "apply gated")
        self.assertIn("no staged update", result.blockers)
        self.assertIn("update application is disabled in this release", result.blockers)

    def test_apply_preflight_reports_staged_update_and_apply_gate(self):
        updates = self._updates_module()
        manager = updates.UpdateManager(current_version="6.6.27")
        staged_path = manager.target_dir / "BookmarkOrganizerPro-6.7.0.tar.gz"
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        staged_path.write_bytes(b"archive")
        manager.staged_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manager.staged_manifest_path.write_text(json.dumps({
            "current_version": "6.6.27",
            "latest_version": "6.7.0",
            "target_name": "BookmarkOrganizerPro-6.7.0.tar.gz",
            "target_path": "BookmarkOrganizerPro-6.7.0.tar.gz",
            "staged_paths": [str(staged_path)],
            "channel": "stable",
            "staged_at": "2026-06-06T00:00:00+00:00",
        }), encoding="utf-8")

        result = manager.apply_preflight()

        self.assertFalse(result.allowed)
        self.assertEqual(result.latest_version, "6.7.0")
        self.assertEqual(result.staged_paths, (str(staged_path.resolve()),))
        self.assertEqual(result.blockers, ("update application is disabled in this release",))

    def test_clear_staged_update_removes_manifest_and_targets(self):
        updates = self._updates_module()
        manager = updates.UpdateManager(current_version="6.6.27")
        staged_path = manager.target_dir / "BookmarkOrganizerPro-6.7.0.tar.gz"
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        staged_path.write_bytes(b"archive")
        manager.staged_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manager.staged_manifest_path.write_text(json.dumps({
            "current_version": "6.6.27",
            "latest_version": "6.7.0",
            "target_name": "BookmarkOrganizerPro-6.7.0.tar.gz",
            "target_path": "BookmarkOrganizerPro-6.7.0.tar.gz",
            "staged_paths": [str(staged_path)],
            "channel": "stable",
            "staged_at": "2026-06-06T00:00:00+00:00",
        }), encoding="utf-8")

        result = manager.clear_staged_update()

        self.assertTrue(result.cleaned)
        self.assertTrue(result.removed_manifest)
        self.assertEqual(result.removed_targets, (str(staged_path.resolve()),))
        self.assertFalse(staged_path.exists())
        self.assertFalse(manager.staged_manifest_path.exists())

    def test_clear_staged_update_reports_empty_state(self):
        updates = self._updates_module()
        manager = updates.UpdateManager(current_version="6.6.27")

        result = manager.clear_staged_update()

        self.assertFalse(result.cleaned)
        self.assertFalse(result.removed_manifest)
        self.assertEqual(result.reason, "no staged update")

    def test_build_apply_plan_reports_no_staged_blockers(self):
        updates = self._updates_module()
        manager = updates.UpdateManager(current_version="6.6.27")

        plan = manager.build_apply_plan(install_dir=manager.cache_dir / "install")

        self.assertFalse(plan.ready)
        self.assertEqual(plan.reason, "apply plan only")
        self.assertIn("no staged update", plan.blockers)
        self.assertIn("update application is disabled in this release", plan.blockers)
        self.assertTrue(any("rollback snapshot" in action for action in plan.actions))

    def test_build_apply_plan_includes_staged_update_paths(self):
        updates = self._updates_module()
        manager = updates.UpdateManager(current_version="6.6.27")
        staged_path = manager.target_dir / "BookmarkOrganizerPro-6.7.0.tar.gz"
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        staged_path.write_bytes(b"archive")
        manager.staged_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manager.staged_manifest_path.write_text(json.dumps({
            "current_version": "6.6.27",
            "latest_version": "6.7.0",
            "target_name": "BookmarkOrganizerPro-6.7.0.tar.gz",
            "target_path": "BookmarkOrganizerPro-6.7.0.tar.gz",
            "staged_paths": [str(staged_path)],
            "channel": "stable",
            "staged_at": "2026-06-06T00:00:00+00:00",
        }), encoding="utf-8")

        plan = manager.build_apply_plan(install_dir=manager.cache_dir / "install")

        self.assertEqual(plan.latest_version, "6.7.0")
        self.assertEqual(plan.staged_paths, (str(staged_path.resolve()),))
        self.assertIn("6.6.27-to-6.7.0", plan.rollback_dir)
        self.assertEqual(plan.blockers, ("update application is disabled in this release",))

    def test_download_update_rejects_target_paths_outside_cache(self):
        updates = self._updates_module()
        manager = updates.UpdateManager(current_version="6.6.27")
        manager.configure(
            enabled=True,
            metadata_url="https://updates.example.com/metadata",
            targets_url="https://updates.example.com/targets",
        )
        manager.metadata_dir.mkdir(parents=True, exist_ok=True)
        manager.trusted_root_path.write_text("{}", encoding="utf-8")

        class FakeTarget:
            version = "6.7.0"
            filename = "BookmarkOrganizerPro-6.7.0.tar.gz"
            target_path_str = "BookmarkOrganizerPro-6.7.0.tar.gz"

        class FakeClient:
            def __init__(self, **kwargs):
                self.new_targets = {}

            def check_for_updates(self, **kwargs):
                self.new_targets = {FakeTarget(): object()}
                return FakeTarget()

            def download_target(self, targetinfo, filepath=None, target_base_url=None):
                escaped = manager.cache_dir / ".." / "escaped.tar.gz"
                return str(escaped)

        with patch.object(updates, "tufup_available", return_value=True):
            result = manager.download_update(client_cls=FakeClient)

        self.assertFalse(result.downloaded)
        self.assertEqual(result.reason, "download failed")
        self.assertIn("escaped the update target cache", result.error)

    def test_version_comparison(self):
        updates = self._updates_module()

        self.assertTrue(updates.is_newer_version("6.7.0", "6.6.27"))
        self.assertFalse(updates.is_newer_version("6.6.27", "6.6.27"))
        self.assertFalse(updates.is_newer_version("6.6.26", "6.6.27"))


# ── 1. EmbeddingService ──────────────────────────────────────────────

class TestEmbeddingChunker(_IsolatedTestBase):
    """Tests for EmbeddingService.chunk_text (pure, no backend needed)."""

    def _svc(self):
        from bookmark_organizer_pro.services.embeddings import EmbeddingService
        return EmbeddingService

    def test_chunk_text_basic(self):
        text = "A" * 3000
        chunks = self._svc().chunk_text(text, chunk_chars=1000, overlap=200)
        self.assertGreater(len(chunks), 1)
        # Verify overlap: each chunk (except the first) should start
        # before the previous chunk ended.
        for i in range(1, len(chunks)):
            prev_end = chunks[i - 1]["char_end"]
            curr_start = chunks[i]["char_start"]
            self.assertLess(curr_start, prev_end,
                            "Chunks should overlap")

    def test_chunk_text_empty(self):
        chunks = self._svc().chunk_text("")
        self.assertEqual(chunks, [])

    def test_chunk_text_short(self):
        chunks = self._svc().chunk_text("Hello world", chunk_chars=5000)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]["text"], "Hello world")

    def test_chunk_text_sentence_boundary(self):
        # Build text with clear sentence breaks; chunk_chars chosen so a
        # naive split would land mid-sentence but the boundary finder can
        # snap to a period.
        sentences = ["This is sentence one. ",
                     "Here is sentence two. ",
                     "And sentence number three. ",
                     "Finally the fourth sentence. "]
        text = "".join(sentences) * 10  # ~280 * 10 = ~2800 chars
        chunks = self._svc().chunk_text(text, chunk_chars=300, overlap=50)
        self.assertGreater(len(chunks), 1)
        # At least one chunk should end at a sentence boundary (period)
        ends_at_period = any(c["text"].rstrip().endswith(".") for c in chunks[:-1])
        self.assertTrue(ends_at_period,
                        "Chunker should break at sentence boundaries")

    def test_stable_hash(self):
        from bookmark_organizer_pro.services.embeddings import EmbeddingService
        h1 = EmbeddingService.stable_hash("hello world")
        h2 = EmbeddingService.stable_hash("hello world")
        h3 = EmbeddingService.stable_hash("different input")
        self.assertEqual(h1, h2, "Same input must produce same hash")
        self.assertNotEqual(h1, h3, "Different input must produce different hash")
        self.assertEqual(len(h1), 64, "SHA-256 hex digest is 64 chars")


class TestChatStreamEvents(_IsolatedTestBase):
    """Tests for RAG chat response event chunking."""

    def test_stream_events_preserve_answer_and_finish_with_metadata(self):
        from bookmark_organizer_pro.services.rag_chat import (
            ChatTurn,
            build_chat_stream_events,
        )

        turn = ChatTurn(
            answer=(
                "One long sentence about bookmarks that should be split into "
                "multiple client-facing chunks without losing any text."
            ),
            sources=[{"bookmark_id": 3}],
            used_chunks=1,
            chunk_provenance=[{"citation_id": "c0", "bookmark_id": 3}],
        )

        events = build_chat_stream_events(turn, chunk_chars=40)
        chunks = [event for event in events if event.type == "chunk"]

        self.assertGreater(len(chunks), 1)
        self.assertEqual("".join(event.text for event in chunks), turn.answer)
        self.assertEqual(events[-1].type, "complete")
        self.assertEqual(events[-1].sources, turn.sources)
        self.assertEqual(events[-1].chunk_provenance, turn.chunk_provenance)

    def test_chunk_size_is_bounded(self):
        from bookmark_organizer_pro.services.rag_chat import normalize_stream_chunk_chars

        self.assertEqual(normalize_stream_chunk_chars(5), 40)
        self.assertEqual(normalize_stream_chunk_chars(5000), 1000)
        self.assertEqual(normalize_stream_chunk_chars("bad"), 160)

    def test_collection_chat_builds_events_from_provider_stream(self):
        from types import SimpleNamespace
        from bookmark_organizer_pro.services.rag_chat import CollectionChat

        class FakeVectorStore:
            embedder = SimpleNamespace(available=True)

            def search(self, question, k=6, restrict_ids=None):
                return [{
                    "bookmark_id": 7,
                    "text": "Source text",
                    "char_start": 0,
                    "char_end": 11,
                }]

        class FakeClient:
            supports_native_streaming = True

            def stream_complete(self, prompt, system="", max_tokens=800, temperature=0.2):
                yield "Streamed "
                yield "answer [#c0]."

        chat = CollectionChat(object(), FakeVectorStore())

        with patch(
            "bookmark_organizer_pro.services.rag_chat.create_ai_client",
            return_value=FakeClient(),
        ):
            result = chat.stream_answer("What is saved?", chunk_chars=80)

        self.assertTrue(result.provider_streaming)
        self.assertEqual(result.turn.answer, "Streamed answer [#c0].")
        chunks = [event for event in result.events if event.type == "chunk"]
        self.assertEqual([event.text for event in chunks], ["Streamed ", "answer [#c0]."])
        self.assertEqual(result.events[-1].type, "complete")
        self.assertEqual(result.events[-1].sources[0]["bookmark_id"], 7)


# ── 2. EncryptedStore ─────────────────────────────────────────────────

class TestEncryptedStore(_IsolatedTestBase):

    def _store(self, passphrase="test-secret-123"):
        from bookmark_organizer_pro.services.encryption import EncryptedStore
        return EncryptedStore(passphrase)

    def test_encrypt_decrypt_roundtrip(self):
        store = self._store()
        original = b'{"bookmarks": [1, 2, 3]}'
        blob = store.encrypt(original)
        recovered = store.decrypt(blob)
        self.assertEqual(recovered, original)

    def test_wrong_key_fails(self):
        store_a = self._store("key-alpha")
        store_b = self._store("key-bravo")
        blob = store_a.encrypt(b"secret data")
        with self.assertRaises(Exception):
            store_b.decrypt(blob)

    def test_encrypt_file_roundtrip(self):
        store = self._store()
        src = Path(self._tmp) / "plain.json"
        src.write_bytes(b'{"hello": "world"}')
        enc_path = store.encrypt_file(src)
        self.assertTrue(enc_path.exists())
        dec_path = Path(self._tmp) / "decrypted.json"
        store.decrypt_file(enc_path, dec_path)
        self.assertEqual(dec_path.read_bytes(), b'{"hello": "world"}')

    def test_decrypt_file_rejects_same_path(self):
        store = self._store()
        src = Path(self._tmp) / "same.json.enc"
        src.write_bytes(store.encrypt(b"data"))
        with self.assertRaises(ValueError):
            store.decrypt_file(src, src)


# ── 3. TagLinter ──────────────────────────────────────────────────────

class TestTagLinter(_IsolatedTestBase):

    def _linter(self):
        from bookmark_organizer_pro.services.tag_linter import TagLinter
        return TagLinter()

    def test_no_issues_with_clean_tags(self):
        bookmarks = [
            _make_bookmark(url="https://a.com", tags=["rust"]),
            _make_bookmark(url="https://b.com", tags=["golang"]),
        ]
        report = self._linter().lint(bookmarks)
        self.assertEqual(len(report.suggestions), 0,
                         "Unique, non-overlapping tags should produce no suggestions")

    def test_detects_case_variants(self):
        bookmarks = [
            _make_bookmark(url="https://a.com", tags=["Python"]),
            _make_bookmark(url="https://b.com", tags=["python"]),
        ]
        report = self._linter().lint(bookmarks)
        self.assertGreater(len(report.suggestions), 0,
                           "'Python' and 'python' should be flagged as near-duplicate")
        variants = set()
        for s in report.suggestions:
            variants.add(s.canonical)
            variants.update(s.variants)
        self.assertIn("Python", variants)
        self.assertIn("python", variants)


# ── 4. FlowManager ───────────────────────────────────────────────────

class TestFlowManager(_IsolatedTestBase):

    def _manager(self):
        from bookmark_organizer_pro.services.flows import FlowManager
        fp = Path(self._tmp) / f"flows_{id(self)}.json"
        return FlowManager(filepath=fp)

    def test_create_flow(self):
        mgr = self._manager()
        flow = mgr.create("Research Trail", description="ML papers")
        self.assertTrue(flow.id)
        self.assertEqual(flow.name, "Research Trail")

    def test_add_step(self):
        mgr = self._manager()
        flow = mgr.create("Trail")
        ok = mgr.add_step(flow.id, bookmark_id=42, note="First read")
        self.assertTrue(ok)
        fetched = mgr.get(flow.id)
        self.assertEqual(len(fetched.steps), 1)
        self.assertEqual(fetched.steps[0].bookmark_id, 42)

    def test_remove_step(self):
        mgr = self._manager()
        flow = mgr.create("Trail")
        mgr.add_step(flow.id, bookmark_id=10)
        mgr.add_step(flow.id, bookmark_id=20)
        ok = mgr.remove_step(flow.id, bookmark_id=10)
        self.assertTrue(ok)
        fetched = mgr.get(flow.id)
        self.assertEqual(len(fetched.steps), 1)
        self.assertEqual(fetched.steps[0].bookmark_id, 20)

    def test_reorder(self):
        mgr = self._manager()
        flow = mgr.create("Trail")
        mgr.add_step(flow.id, bookmark_id=1)
        mgr.add_step(flow.id, bookmark_id=2)
        mgr.add_step(flow.id, bookmark_id=3)
        ok = mgr.reorder(flow.id, [3, 1, 2])
        self.assertTrue(ok)
        fetched = mgr.get(flow.id)
        ids_in_order = [s.bookmark_id for s in fetched.steps]
        self.assertEqual(ids_in_order, [3, 1, 2])

    def test_delete_flow(self):
        mgr = self._manager()
        flow = mgr.create("Temp")
        self.assertIsNotNone(mgr.get(flow.id))
        ok = mgr.delete(flow.id)
        self.assertTrue(ok)
        self.assertIsNone(mgr.get(flow.id))


# ── 5. DailyDigestService ────────────────────────────────────────────

class TestDailyDigest(_IsolatedTestBase):

    def _svc(self):
        from bookmark_organizer_pro.services.digest import DailyDigestService
        return DailyDigestService()

    def test_build_empty(self):
        digest = self._svc().build([])
        self.assertIsInstance(digest.sections, list)
        self.assertEqual(len(digest.sections), 0,
                         "No bookmarks should yield no digest sections")
        self.assertTrue(digest.generated_at)

    def test_build_with_bookmarks(self):
        today = datetime.now()
        # Bookmark saved on this day last year -> "On this day" section
        last_year = today.replace(year=today.year - 1)
        bm_old = _make_bookmark(
            url="https://old.com",
            title="Old",
            created_at=last_year.isoformat(),
        )
        # Bookmark from 200 days ago, not archived -> "Rediscover" candidate
        bm_rediscover = _make_bookmark(
            url="https://rediscover.com",
            title="Rediscover Me",
            created_at=(today - timedelta(days=200)).isoformat(),
        )
        digest = self._svc().build([bm_old, bm_rediscover], today=today)
        self.assertTrue(digest.generated_at)
        section_titles = [s.title for s in digest.sections]
        # At least one of the heuristic sections should fire
        self.assertGreater(len(digest.sections), 0)
        # "On this day" should fire for bm_old
        self.assertIn("On this day", section_titles)


# ── 6. RSS feeds ──────────────────────────────────────────────────────

class TestParseFeed(_IsolatedTestBase):

    def test_parse_rss2_feed(self):
        from bookmark_organizer_pro.services.rss_feeds import parse_feed

        xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>First Post</title>
      <link>https://blog.example.com/post-1</link>
      <description>Summary of post 1</description>
      <guid>guid-001</guid>
    </item>
    <item>
      <title>Second Post</title>
      <link>https://blog.example.com/post-2</link>
    </item>
  </channel>
</rss>"""
        items = parse_feed(xml)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].title, "First Post")
        self.assertEqual(items[0].link, "https://blog.example.com/post-1")
        self.assertEqual(items[0].guid, "guid-001")

    def test_parse_atom_feed(self):
        from bookmark_organizer_pro.services.rss_feeds import parse_feed

        xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Atom Feed</title>
  <entry>
    <title>Atom Entry</title>
    <link href="https://atom.example.com/entry-1"/>
    <id>urn:uuid:atom-001</id>
    <summary>Atom summary</summary>
    <updated>2025-01-01T00:00:00Z</updated>
  </entry>
</feed>"""
        items = parse_feed(xml)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "Atom Entry")
        self.assertEqual(items[0].link, "https://atom.example.com/entry-1")
        self.assertEqual(items[0].guid, "urn:uuid:atom-001")


class TestOPDSExport(_IsolatedTestBase):
    def test_export_opds_acquisition_feed(self):
        from bookmark_organizer_pro.services.feed_export import export_opds

        bm = _make_bookmark(
            id=123,
            url="https://example.com/book.epub",
            title="Example Book",
            description="Readable export",
            category="Books",
            tags=["Fiction"],
            language="en",
        )
        output = Path(self._tmp) / "catalog.opds.xml"

        path = export_opds(
            [bm],
            title="Read Later",
            output_path=output,
            catalog_url="https://localhost/opds.xml",
        )
        xml = path.read_text(encoding="utf-8")

        self.assertIn('profile=opds-catalog;kind=acquisition', xml)
        self.assertIn('http://opds-spec.org/acquisition/open-access', xml)
        self.assertIn('application/epub+zip', xml)
        self.assertIn('<dc:language>en</dc:language>', xml)
        self.assertIn('Example Book', xml)


class TestFeedRegistry(_IsolatedTestBase):

    def _registry(self):
        from bookmark_organizer_pro.services.rss_feeds import FeedRegistry
        fp = Path(self._tmp) / f"feeds_{id(self)}.json"
        return FeedRegistry(filepath=fp)

    @patch("bookmark_organizer_pro.url_utils.URLUtilities._is_safe_url",
           return_value=True)
    def test_feed_registry_crud(self, _mock_safe):
        reg = self._registry()
        cfg = reg.add(url="https://blog.example.com/feed.xml",
                      name="Example Blog",
                      default_tags=["blog"],
                      ai_mode="DISABLED")
        self.assertTrue(cfg.id)
        self.assertEqual(cfg.name, "Example Blog")

        # get
        fetched = reg.get(cfg.id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.url, "https://blog.example.com/feed.xml")

        # list
        all_feeds = reg.list_feeds()
        self.assertEqual(len(all_feeds), 1)

        # remove
        ok = reg.remove(cfg.id)
        self.assertTrue(ok)
        self.assertIsNone(reg.get(cfg.id))
        self.assertEqual(len(reg.list_feeds()), 0)


# ── 7. ZipExporter ───────────────────────────────────────────────────

class TestZipExporter(_IsolatedTestBase):

    def test_export_one(self):
        from bookmark_organizer_pro.services.zip_export import ZipExporter

        exports = Path(self._tmp) / "exports_test"
        exports.mkdir(exist_ok=True)
        exporter = ZipExporter(exports_dir=exports)

        bm = _make_bookmark(url="https://zip-test.com", title="ZIP Test")
        ok, path_str = exporter.export_one(bm)
        self.assertTrue(ok)
        zip_path = Path(path_str)
        self.assertTrue(zip_path.exists())

        with zipfile.ZipFile(zip_path) as z:
            names = z.namelist()
            self.assertIn("metadata.json", names)
            self.assertIn("notes.md", names)
            meta = json.loads(z.read("metadata.json"))
            self.assertEqual(meta["url"], "https://zip-test.com")


# ── 8. ReadLaterQueue ─────────────────────────────────────────────────

class TestReadLaterQueue(_IsolatedTestBase):

    def _queue(self):
        from bookmark_organizer_pro.services.read_later import ReadLaterQueue
        return ReadLaterQueue()

    def test_enqueue_dequeue(self):
        q = self._queue()
        bm = _make_bookmark(url="https://readlater.com", title="Read Later")
        self.assertFalse(bm.read_later)

        q.enqueue(bm, position=0)
        self.assertTrue(bm.read_later)

        # list_queue should include it
        queue_list = q.list_queue([bm])
        self.assertEqual(len(queue_list), 1)
        self.assertEqual(queue_list[0].url, "https://readlater.com")

        q.dequeue(bm)
        self.assertFalse(bm.read_later)
        self.assertEqual(q.list_queue([bm]), [])

    def test_peek_next(self):
        q = self._queue()
        bm1 = _make_bookmark(url="https://a.com", title="A")
        bm2 = _make_bookmark(url="https://b.com", title="B")
        q.enqueue(bm1, position=1)
        q.enqueue(bm2, position=0)
        nxt = q.peek_next([bm1, bm2])
        self.assertIsNotNone(nxt)
        self.assertEqual(nxt.url, "https://b.com",
                         "peek_next should return the lowest-position item")

    def test_complete(self):
        q = self._queue()
        bm = _make_bookmark(url="https://done.com", title="Done")
        q.enqueue(bm)
        q.complete(bm)
        self.assertFalse(bm.read_later)
        self.assertGreater(bm.visit_count, 0)

    def test_reorder(self):
        q = self._queue()
        bm1 = _make_bookmark(url="https://r1.com", title="R1")
        bm2 = _make_bookmark(url="https://r2.com", title="R2")
        q.enqueue(bm1, position=0)
        q.enqueue(bm2, position=1)
        moved = q.reorder([bm1, bm2], [bm2.id, bm1.id])
        self.assertGreater(moved, 0)
        # After reorder, bm2 should be position 0
        self.assertEqual(bm2.read_later_position, 0)
        self.assertEqual(bm1.read_later_position, 1)


# ── 9. HybridSearch (keyword-only fallback) ─────────────────────────

class TestHybridSearchFallback(_IsolatedTestBase):
    """Tests for HybridSearch keyword-only path (no embedding backend)."""

    def test_keyword_search_returns_results(self):
        from bookmark_organizer_pro.services.hybrid_search import HybridSearch
        from bookmark_organizer_pro.services.vector_store import VectorStore
        from bookmark_organizer_pro.services.embeddings import EmbeddingService

        emb = EmbeddingService()
        vs = VectorStore(emb)
        hs = HybridSearch(vs)
        bms = [
            _make_bookmark(url="https://python.org", title="Python Programming"),
            _make_bookmark(url="https://rust-lang.org", title="Rust Language"),
        ]
        results = hs.search(bms, "python")
        titles = [r.bookmark.title for r in results]
        self.assertIn("Python Programming", titles)

    def test_empty_query(self):
        from bookmark_organizer_pro.services.hybrid_search import HybridSearch
        from bookmark_organizer_pro.services.vector_store import VectorStore
        from bookmark_organizer_pro.services.embeddings import EmbeddingService

        emb = EmbeddingService()
        vs = VectorStore(emb)
        hs = HybridSearch(vs)
        results = hs.search([], "")
        self.assertEqual(results, [])


# ── 10. NLQueryTranslator ───────────────────────────────────────────

class TestNLQueryHeuristic(_IsolatedTestBase):
    """Tests for the heuristic fallback (no AI) of NLQueryTranslator."""

    def test_heuristic_extracts_tags(self):
        from bookmark_organizer_pro.services.nl_query import NLQueryTranslator
        nlt = NLQueryTranslator(ai_config=None)
        q = nlt.heuristic_parse("bookmarks tagged python")
        self.assertIn("python", q.get("tags", []) + [q.get("keyword", "")])

    def test_heuristic_with_domain(self):
        from bookmark_organizer_pro.services.nl_query import NLQueryTranslator
        nlt = NLQueryTranslator(ai_config=None)
        q = nlt.heuristic_parse("github.com links")
        text = json.dumps(q)
        self.assertIn("github", text.lower())


# ── 11. DeadLinkScanner ─────────────────────────────────────────────

class TestDeadLinkScanner(_IsolatedTestBase):
    """Tests for DeadLinkScanner initialization and result storage."""

    def test_list_dead_links_empty(self):
        from bookmark_organizer_pro.services.dead_link_scanner import DeadLinkScanner
        scanner = DeadLinkScanner(get_bookmarks=lambda: [])
        self.assertEqual(scanner.list_dead_links(), [])

    def test_scanner_stores_results(self):
        from bookmark_organizer_pro.services.dead_link_scanner import DeadLinkScanner
        scanner = DeadLinkScanner(get_bookmarks=lambda: [])
        scanner._results = {"https://dead.example.com": {
            "url": "https://dead.example.com",
            "status": 404,
            "checked_at": datetime.now().isoformat(),
        }}
        scanner._save_results()
        scanner2 = DeadLinkScanner(get_bookmarks=lambda: [])
        self.assertEqual(len(scanner2._results), 0)


# ── 12. WallabagJSONImporter ────────────────────────────────────────

class TestWallabagImporter(_IsolatedTestBase):
    """Tests for the Wallabag JSON importer."""

    def test_import_basic(self):
        from bookmark_organizer_pro.importers_extra import WallabagJSONImporter
        data = [
            {
                "url": "https://example.com/article",
                "title": "Test Article",
                "is_starred": 1,
                "tags": [{"label": "python", "slug": "python"}],
                "created_at": "2026-01-15T10:00:00+00:00",
            },
            {
                "url": "https://example.com/page",
                "title": "Test Page",
                "is_starred": 0,
                "tags": [],
            },
        ]
        p = Path(self._tmp) / "wallabag_export.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        importer = WallabagJSONImporter()
        bms = list(importer.from_path(str(p)))
        self.assertEqual(len(bms), 2)
        self.assertEqual(bms[0].title, "Test Article")
        self.assertTrue(bms[0].is_pinned)
        self.assertIn("python", bms[0].tags)
        self.assertFalse(bms[1].is_pinned)

    def test_import_empty_file(self):
        from bookmark_organizer_pro.importers_extra import WallabagJSONImporter
        p = Path(self._tmp) / "wallabag_empty.json"
        p.write_text("[]", encoding="utf-8")
        bms = list(WallabagJSONImporter().from_path(str(p)))
        self.assertEqual(len(bms), 0)

    def test_import_missing_file(self):
        from bookmark_organizer_pro.importers_extra import WallabagJSONImporter
        bms = list(WallabagJSONImporter().from_path("/nonexistent.json"))
        self.assertEqual(len(bms), 0)


# ── 13. ArcBrowserImporter ──────────────────────────────────────────

class TestArcImporter(_IsolatedTestBase):
    """Tests for the Arc Browser sidebar importer."""

    def test_import_basic(self):
        from bookmark_organizer_pro.importers_extra import ArcBrowserImporter
        data = [
            {"data": {"tab": {
                "savedURL": "https://example.com",
                "savedTitle": "Example",
            }}},
            {"data": {"tab": {
                "savedURL": "https://github.com",
                "savedTitle": "GitHub",
            }}},
        ]
        p = Path(self._tmp) / "StorableSidebar.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        bms = list(ArcBrowserImporter().from_path(str(p)))
        self.assertEqual(len(bms), 2)
        self.assertEqual(bms[0].title, "Example")
        self.assertEqual(bms[1].url, "https://github.com")

    def test_import_nested_format(self):
        from bookmark_organizer_pro.importers_extra import ArcBrowserImporter
        data = {"sidebarItems": [
            {"data": {"tab": {
                "savedURL": "https://nested.example.com",
                "savedTitle": "Nested",
            }}},
        ]}
        p = Path(self._tmp) / "arc_nested.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        bms = list(ArcBrowserImporter().from_path(str(p)))
        self.assertEqual(len(bms), 1)


# ── 14. Batch save context manager ──────────────────────────────────

class TestBatchSave(_IsolatedTestBase):
    """Tests for BookmarkManager.batch() context manager."""

    def _manager(self):
        from bookmark_organizer_pro.core import CategoryManager, StorageManager
        from bookmark_organizer_pro.managers import BookmarkManager, TagManager
        fp = Path(self._tmp) / "batch_test_bookmarks.json"
        cm = CategoryManager()
        tm = TagManager()
        return BookmarkManager(cm, tm, filepath=fp)

    def test_batch_suppresses_saves(self):
        mgr = self._manager()
        save_count = [0]
        orig_save = mgr.storage.save
        def counting_save(*a, **k):
            save_count[0] += 1
            orig_save(*a, **k)
        mgr.storage.save = counting_save

        with mgr.batch():
            mgr.add_bookmark(_make_bookmark(url="https://a.com"), save=True)
            mgr.add_bookmark(_make_bookmark(url="https://b.com"), save=True)
            mgr.add_bookmark(_make_bookmark(url="https://c.com"), save=True)
        self.assertEqual(save_count[0], 1)

    def test_batch_nestable(self):
        mgr = self._manager()
        save_count = [0]
        orig_save = mgr.storage.save
        def counting_save(*a, **k):
            save_count[0] += 1
            orig_save(*a, **k)
        mgr.storage.save = counting_save

        with mgr.batch():
            mgr.add_bookmark(_make_bookmark(url="https://d.com"), save=True)
            with mgr.batch():
                mgr.add_bookmark(_make_bookmark(url="https://e.com"), save=True)
        self.assertEqual(save_count[0], 1)


class TestBookmarkManagerSQLiteStorage(_IsolatedTestBase):
    """Tests for opt-in SQLite storage backend selection."""

    def _manager(self, filepath, storage_backend=None):
        from bookmark_organizer_pro.core import CategoryManager
        from bookmark_organizer_pro.managers import BookmarkManager, TagManager
        return BookmarkManager(
            CategoryManager(),
            TagManager(),
            filepath=filepath,
            storage_backend=storage_backend,
        )

    def test_explicit_sqlite_backend_persists_and_reloads(self):
        from bookmark_organizer_pro.core import SQLiteStorageManager

        fp = Path(self._tmp) / "library.json"
        mgr = self._manager(fp, storage_backend="sqlite")

        self.assertEqual(mgr.storage_backend, "sqlite")
        self.assertEqual(mgr.filepath, fp.with_suffix(".sqlite"))
        self.assertIsInstance(mgr.storage, SQLiteStorageManager)

        mgr.add_bookmark(_make_bookmark(url="https://sqlite-manager.example", title="SQLite Manager"))
        reloaded = self._manager(fp, storage_backend="sqlite")

        self.assertEqual(len(reloaded.get_all_bookmarks()), 1)
        self.assertEqual(reloaded.get_all_bookmarks()[0].url, "https://sqlite-manager.example")

    def test_sqlite_suffix_selects_sqlite_backend(self):
        from bookmark_organizer_pro.core import SQLiteStorageManager

        mgr = self._manager(Path(self._tmp) / "library.sqlite")

        self.assertEqual(mgr.storage_backend, "sqlite")
        self.assertIsInstance(mgr.storage, SQLiteStorageManager)

    def test_storage_backend_env_selects_sqlite(self):
        fp = Path(self._tmp) / "env_library.json"
        with patch.dict(os.environ, {"BOOKMARK_STORAGE_BACKEND": "sqlite"}):
            mgr = self._manager(fp)

        self.assertEqual(mgr.storage_backend, "sqlite")
        self.assertEqual(mgr.filepath, fp.with_suffix(".sqlite"))


# ── 15. Bookmark graph ──────────────────────────────────────────────

class TestBookmarkGraph(_IsolatedTestBase):
    """Tests for bookmark relationship graph construction and export."""

    def test_graph_builds_bookmark_tag_category_domain_edges(self):
        from bookmark_organizer_pro.services.bookmark_graph import build_bookmark_graph

        bookmarks = [
            _make_bookmark(id=1, url="https://docs.python.org", title="Python Docs",
                           category="Development / Python", tags=["python", "docs"]),
            _make_bookmark(id=2, url="https://realpython.com", title="Real Python",
                           category="Development / Python", tags=["python"]),
        ]

        graph = build_bookmark_graph(bookmarks)
        node_ids = {node.id for node in graph.nodes}
        edge_kinds = {edge.kind for edge in graph.edges}

        self.assertIn("bookmark:1", node_ids)
        self.assertIn("tag:python", node_ids)
        self.assertIn("category:development-python", node_ids)
        self.assertIn("domain:docs.python.org", node_ids)
        self.assertTrue({"tag", "category", "domain"}.issubset(edge_kinds))

    def test_force_layout_and_export_json(self):
        from bookmark_organizer_pro.services.bookmark_graph import (
            apply_force_layout,
            build_bookmark_graph,
            export_bookmark_graph_json,
        )

        bookmarks = [
            _make_bookmark(id=3, url="https://example.com/a", title="A", tags=["alpha"]),
            _make_bookmark(id=4, url="https://example.com/b", title="B", tags=["beta"]),
        ]
        graph = apply_force_layout(build_bookmark_graph(bookmarks), width=400, height=300, iterations=10)

        self.assertTrue(all(36 <= node.x <= 364 for node in graph.nodes))
        self.assertTrue(all(36 <= node.y <= 264 for node in graph.nodes))

        out = export_bookmark_graph_json(bookmarks, Path(self._tmp) / "bookmark-graph.json")
        payload = json.loads(out.read_text(encoding="utf-8"))
        self.assertIn("nodes", payload)
        self.assertIn("edges", payload)


# ── 16. Reader annotations ──────────────────────────────────────────

class TestReaderAnnotations(_IsolatedTestBase):
    """Tests for reader highlight storage and Markdown export."""

    def setUp(self):
        self.filepath = Path(self._tmp) / "reader_annotations_test.json"
        if self.filepath.exists():
            self.filepath.unlink()

    def test_add_highlight_from_text_persists_and_lists(self):
        from bookmark_organizer_pro.services.reader_annotations import ReaderAnnotationStore

        store = ReaderAnnotationStore(self.filepath)
        highlight = store.add_from_text(
            bookmark_id=42,
            text="Intro selected passage outro",
            char_start=6,
            char_end=22,
            color="blue",
            note="Keep this",
        )

        reloaded = ReaderAnnotationStore(self.filepath)
        items = reloaded.list_for_bookmark(42)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].id, highlight.id)
        self.assertEqual(items[0].text, "selected passage")
        self.assertEqual(items[0].color, "blue")
        self.assertEqual(items[0].note, "Keep this")

    def test_add_for_bookmark_validates_extracted_text_range(self):
        from bookmark_organizer_pro.services.reader_annotations import ReaderAnnotationStore

        text_path = Path(self._tmp) / "reader-source.txt"
        text_path.write_text("Short extracted text", encoding="utf-8")
        bookmark = _make_bookmark(id=7, extracted_text_path=str(text_path))
        store = ReaderAnnotationStore(self.filepath)

        highlight = store.add_for_bookmark(bookmark, 0, 5, color="green")

        self.assertEqual(highlight.text, "Short")
        self.assertEqual(highlight.color, "green")
        with self.assertRaises(ValueError):
            store.add_for_bookmark(bookmark, 0, 999)

    def test_export_highlights_markdown_contains_quote_and_note(self):
        from bookmark_organizer_pro.services.reader_annotations import (
            ReaderAnnotationStore,
            export_bookmark_highlights,
        )

        bookmark = _make_bookmark(id=9, title="Reader / Source", url="https://example.com/reader")
        store = ReaderAnnotationStore(self.filepath)
        highlight = store.add_from_text(9, "Alpha beta gamma", 6, 10, note="Important")

        out_path = export_bookmark_highlights(bookmark, [highlight], output_dir=Path(self._tmp) / "reader_exports")
        text = out_path.read_text(encoding="utf-8")

        self.assertIn("# Reader highlights: Reader / Source", text)
        self.assertIn("> beta", text)
        self.assertIn("Important", text)


# ── 17. SnapshotArchiver (chain preference) ─────────────────────────

class TestSnapshotArchiver(_IsolatedTestBase):
    """Tests for SnapshotArchiver initialization and preferences."""

    def test_archiver_initializes(self):
        from bookmark_organizer_pro.services.snapshot import SnapshotArchiver
        archiver = SnapshotArchiver()
        self.assertIsNotNone(archiver)
        self.assertTrue(hasattr(archiver, 'archive'))

    def test_max_bytes_limit(self):
        from bookmark_organizer_pro.services.snapshot import SnapshotArchiver
        archiver = SnapshotArchiver()
        self.assertGreater(archiver.MAX_BYTES, 0)
        self.assertLessEqual(archiver.MAX_BYTES, 50_000_000)


# ── 18. Embedding model config ──────────────────────────────────────

class TestEmbeddingModels(_IsolatedTestBase):
    """Tests for the RECOMMENDED_MODELS config."""

    def test_recommended_models_present(self):
        from bookmark_organizer_pro.services.embeddings import RECOMMENDED_MODELS
        self.assertIn("default", RECOMMENDED_MODELS)
        self.assertIn("nomic", RECOMMENDED_MODELS)
        self.assertIn("minilm", RECOMMENDED_MODELS)

    def test_nomic_config(self):
        from bookmark_organizer_pro.services.embeddings import RECOMMENDED_MODELS, NOMIC_MODEL
        nomic = RECOMMENDED_MODELS["nomic"]
        self.assertEqual(nomic["model"], NOMIC_MODEL)
        self.assertEqual(nomic["dims"], 768)


if __name__ == "__main__":
    unittest.main()
