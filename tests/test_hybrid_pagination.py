"""Hybrid search paging and LanceDB full-text index options."""

from __future__ import annotations

import unittest
from typing import Any, Dict, List

from bookmark_organizer_pro.models import Bookmark
from bookmark_organizer_pro.services.hybrid_search import HybridSearch


class _StubKeywordEngine:
    def __init__(self, ordering):
        self.ordering = ordering

    def search(self, bookmarks, query):
        lookup = {b.id: b for b in bookmarks}
        return [(lookup[bid], 1.0 - index * 0.01)
                for index, bid in enumerate(self.ordering) if bid in lookup]


class _StubVectorStore:
    def __init__(self, semantic=(), fts=()):
        self.semantic = list(semantic)
        self.fts = list(fts)
        self.fts_calls: List[Dict[str, Any]] = []

    def search(self, query, k=50):
        return [{"bookmark_id": bid, "text": f"snippet {bid}"} for bid in self.semantic[:k]]

    def fts_search(self, query, k=50, offset=0):
        self.fts_calls.append({"k": k, "offset": offset})
        return self.fts[offset:offset + k]


def _bookmarks(count):
    return [Bookmark(id=i, url=f"https://page{i}.test/", title=f"Page {i}") for i in range(count)]


class TestHybridPagination(unittest.TestCase):
    def _service(self, ids, semantic=None, fts=None):
        service = HybridSearch.__new__(HybridSearch)
        service.keyword_engine = _StubKeywordEngine(ids)
        service.vector_store = _StubVectorStore(
            semantic if semantic is not None else ids,
            fts if fts is not None else ids,
        )
        return service

    def test_pages_do_not_overlap_or_skip(self):
        bookmarks = _bookmarks(20)
        ids = [b.id for b in bookmarks]
        service = self._service(ids)

        first = service.search(bookmarks, "query", limit=5)
        second = service.search(bookmarks, "query", limit=5, offset=5)
        third = service.search(bookmarks, "query", limit=5, offset=10)

        first_ids = [r.bookmark.id for r in first]
        second_ids = [r.bookmark.id for r in second]
        third_ids = [r.bookmark.id for r in third]

        self.assertEqual(len(first_ids), 5)
        self.assertEqual(len(second_ids), 5)
        self.assertEqual(set(first_ids) & set(second_ids), set())
        self.assertEqual(set(second_ids) & set(third_ids), set())

        combined = service.search(bookmarks, "query", limit=15)
        self.assertEqual(first_ids + second_ids + third_ids,
                         [r.bookmark.id for r in combined])

    def test_offset_past_the_end_returns_nothing(self):
        bookmarks = _bookmarks(6)
        service = self._service([b.id for b in bookmarks])
        self.assertEqual(service.search(bookmarks, "query", limit=5, offset=99), [])

    def test_keyword_only_path_also_pages(self):
        bookmarks = _bookmarks(10)
        ids = [b.id for b in bookmarks]
        service = self._service(ids, semantic=[], fts=[])

        first = [r.bookmark.id for r in service.search(bookmarks, "query", limit=3)]
        second = [r.bookmark.id for r in service.search(bookmarks, "query", limit=3, offset=3)]

        self.assertEqual(first, ids[:3])
        self.assertEqual(second, ids[3:6])

    def test_zero_and_negative_offsets_behave_like_the_first_page(self):
        bookmarks = _bookmarks(8)
        service = self._service([b.id for b in bookmarks])

        base = [r.bookmark.id for r in service.search(bookmarks, "query", limit=4)]
        for offset in (0, -5, None):
            with self.subTest(offset=offset):
                page = [r.bookmark.id for r in
                        service.search(bookmarks, "query", limit=4, offset=offset)]
                self.assertEqual(page, base)


class _FakeSearch:
    def __init__(self, rows, supports_offset=True):
        self.rows = rows
        self.supports_offset = supports_offset
        self._limit = len(rows)
        self._offset = 0

    def limit(self, value):
        self._limit = value
        return self

    def offset(self, value):
        if not self.supports_offset:
            raise AttributeError("offset is unsupported in this build")
        self._offset = value
        return self

    def to_list(self):
        return self.rows[self._offset:self._offset + self._limit]


class _FakeTable:
    def __init__(self, rows, supports_offset=True, supports_options=True):
        self.rows = rows
        self.supports_offset = supports_offset
        self.supports_options = supports_options
        self.index_calls: List[Dict[str, Any]] = []

    def create_fts_index(self, column, **kwargs):
        if not self.supports_options and set(kwargs) - {"replace"}:
            raise TypeError("unexpected keyword argument")
        self.index_calls.append({"column": column, **kwargs})

    def search(self, query, query_type="fts"):
        return _FakeSearch(self.rows, self.supports_offset)


class TestFtsIndexOptions(unittest.TestCase):
    def _store(self, table):
        from bookmark_organizer_pro.services.vector_store import VectorStore

        store = VectorStore.__new__(VectorStore)
        store.fts_language = "English"
        store.fts_remove_stop_words = True
        store.fts_ascii_folding = True
        store._fts_indexed = False
        return store, table

    def test_index_is_built_with_stop_word_and_folding_options(self):
        table = _FakeTable(rows=[])
        store, table = self._store(table)
        store._create_fts_index(table)

        self.assertEqual(len(table.index_calls), 1)
        call = table.index_calls[0]
        self.assertTrue(call["replace"])
        self.assertTrue(call["remove_stop_words"])
        self.assertEqual(call["language"], "English")
        self.assertTrue(call["ascii_folding"])

    def test_an_older_lancedb_falls_back_to_a_plain_index(self):
        table = _FakeTable(rows=[], supports_options=False)
        store, table = self._store(table)
        store._create_fts_index(table)

        self.assertEqual(len(table.index_calls), 1)
        self.assertEqual(table.index_calls[0], {"column": "text", "replace": True})

    def test_stop_word_removal_can_be_disabled(self):
        table = _FakeTable(rows=[])
        store, table = self._store(table)
        store.fts_remove_stop_words = False
        store._create_fts_index(table)

        self.assertNotIn("remove_stop_words", table.index_calls[0])


if __name__ == "__main__":
    unittest.main()
