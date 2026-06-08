"""Tests for the disaster-recovery safepoint/backup system."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bookmark_organizer_pro.core.storage_manager as sm


class TestSafepoints(unittest.TestCase):
    def _mgr(self):
        tmp = Path(tempfile.mkdtemp())
        backups = tmp / "backups"
        for attr, val in (("BACKUP_DIR", backups), ("SAFEPOINT_DIR", backups / "safepoints")):
            p = patch.object(sm, attr, val)
            p.start()
            self.addCleanup(p.stop)
        return sm.StorageManager(tmp / "master_bookmarks.json")

    def test_safepoint_create_list_restore(self):
        st = self._mgr()
        st.save([{"url": "https://a.com", "title": "A", "id": 1}])
        name = st.create_safepoint("startup")
        self.assertTrue(name and name.startswith("safepoints/"))
        self.assertIn(name, [n for n, _, _ in st.get_backups()])

        st.save([])  # simulate an accidental wipe
        self.assertTrue(st.restore_backup(name))
        data = json.loads(st.filepath.read_text(encoding="utf-8"))["data"]
        self.assertEqual([b["title"] for b in data], ["A"])

    def test_safepoints_survive_per_save_rotation(self):
        """The rolling backups cap at 10; safepoints must outlive that."""
        st = self._mgr()
        st.save([{"url": "https://a.com", "title": "A", "id": 1}])
        sp = st.create_safepoint("pre-import")
        for _ in range(15):  # would rotate out the 10 auto-backups
            st.save([{"url": "https://a.com", "title": "A", "id": 1}])
        self.assertIn(sp, [n for n, _, _ in st.get_backups()])

    def test_restore_blocks_path_traversal(self):
        st = self._mgr()
        st.save([{"url": "https://a.com", "title": "A", "id": 1}])
        self.assertFalse(st.restore_backup("../../../etc/passwd"))
        self.assertFalse(st.restore_backup("safepoints/../../escape.json"))

    def test_create_safepoint_no_file_is_safe(self):
        st = self._mgr()  # nothing saved yet
        self.assertIsNone(st.create_safepoint("startup"))


if __name__ == "__main__":
    unittest.main()
