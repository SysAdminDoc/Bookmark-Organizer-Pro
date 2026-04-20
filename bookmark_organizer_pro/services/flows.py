"""Flows — ordered, annotated bookmark sequences.

Inspired by Grimoire's "Flows" feature. A Flow is a curated, ordered list
of bookmarks with optional per-step notes, representing a research trail,
learning path, or topic deep-dive. Different mental model from tags +
folders, and fits naturally as a Tk tree-view.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from bookmark_organizer_pro.constants import FLOWS_FILE
from bookmark_organizer_pro.logging_config import log
from bookmark_organizer_pro.models import Bookmark


@dataclass
class FlowStep:
    bookmark_id: int
    note: str = ""
    position: int = 0


@dataclass
class Flow:
    id: str
    name: str
    description: str = ""
    color: str = "#58a6ff"
    icon: str = ""
    created_at: str = ""
    modified_at: str = ""
    steps: List[FlowStep] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "color": self.color, "icon": self.icon,
            "created_at": self.created_at, "modified_at": self.modified_at,
            "steps": [asdict(s) for s in self.steps],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Flow":
        steps = [FlowStep(**s) for s in d.get("steps", []) if isinstance(s, dict)]
        return cls(
            id=str(d.get("id") or uuid.uuid4().hex),
            name=str(d.get("name") or "Untitled"),
            description=str(d.get("description") or ""),
            color=str(d.get("color") or "#58a6ff"),
            icon=str(d.get("icon") or ""),
            created_at=str(d.get("created_at") or datetime.now().isoformat()),
            modified_at=str(d.get("modified_at") or datetime.now().isoformat()),
            steps=steps,
        )


class FlowManager:
    """Persisted flow CRUD."""

    def __init__(self, filepath: Path = FLOWS_FILE):
        self.filepath = Path(filepath)
        self._lock = threading.RLock()
        self._flows: Dict[str, Flow] = {}
        self._load()

    # ---------- IO ----------
    def _load(self):
        if not self.filepath.exists():
            return
        try:
            data = json.loads(self.filepath.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning(f"Could not load flows: {exc}")
            return
        with self._lock:
            self._flows = {}
            for d in data if isinstance(data, list) else []:
                try:
                    flow = Flow.from_dict(d)
                    self._flows[flow.id] = flow
                except Exception as exc:
                    log.warning(f"Bad flow entry: {exc}")

    def _save(self):
        with self._lock:
            payload = [f.to_dict() for f in self._flows.values()]
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.filepath.parent, suffix=".tmp", text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.filepath)
        except Exception:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    # ---------- CRUD ----------
    def create(self, name: str, description: str = "",
               color: str = "#58a6ff", icon: str = "") -> Flow:
        now = datetime.now().isoformat()
        flow = Flow(
            id=uuid.uuid4().hex, name=name, description=description,
            color=color, icon=icon, created_at=now, modified_at=now,
        )
        with self._lock:
            self._flows[flow.id] = flow
        self._save()
        return flow

    def delete(self, flow_id: str) -> bool:
        with self._lock:
            if flow_id not in self._flows:
                return False
            del self._flows[flow_id]
        self._save()
        return True

    def rename(self, flow_id: str, name: str) -> bool:
        with self._lock:
            flow = self._flows.get(flow_id)
            if not flow:
                return False
            flow.name = name
            flow.modified_at = datetime.now().isoformat()
        self._save()
        return True

    def get(self, flow_id: str) -> Optional[Flow]:
        return self._flows.get(flow_id)

    def list_flows(self) -> List[Flow]:
        return list(self._flows.values())

    # ---------- steps ----------
    def add_step(self, flow_id: str, bookmark_id: int, note: str = "",
                 position: Optional[int] = None) -> bool:
        with self._lock:
            flow = self._flows.get(flow_id)
            if not flow:
                return False
            if any(s.bookmark_id == bookmark_id for s in flow.steps):
                return False
            pos = position if position is not None else len(flow.steps)
            flow.steps.insert(pos, FlowStep(bookmark_id=bookmark_id,
                                            note=note, position=pos))
            self._renumber(flow)
            flow.modified_at = datetime.now().isoformat()
        self._save()
        return True

    def remove_step(self, flow_id: str, bookmark_id: int) -> bool:
        with self._lock:
            flow = self._flows.get(flow_id)
            if not flow:
                return False
            before = len(flow.steps)
            flow.steps = [s for s in flow.steps if s.bookmark_id != bookmark_id]
            if len(flow.steps) == before:
                return False
            self._renumber(flow)
            flow.modified_at = datetime.now().isoformat()
        self._save()
        return True

    def reorder(self, flow_id: str, bookmark_ids_in_order: List[int]) -> bool:
        with self._lock:
            flow = self._flows.get(flow_id)
            if not flow:
                return False
            existing = {s.bookmark_id: s for s in flow.steps}
            new_steps: List[FlowStep] = []
            for bid in bookmark_ids_in_order:
                step = existing.pop(bid, None)
                if step is not None:
                    new_steps.append(step)
            new_steps.extend(existing.values())  # any not listed go to the end
            flow.steps = new_steps
            self._renumber(flow)
            flow.modified_at = datetime.now().isoformat()
        self._save()
        return True

    def set_note(self, flow_id: str, bookmark_id: int, note: str) -> bool:
        with self._lock:
            flow = self._flows.get(flow_id)
            if not flow:
                return False
            for s in flow.steps:
                if s.bookmark_id == bookmark_id:
                    s.note = note
                    flow.modified_at = datetime.now().isoformat()
                    break
            else:
                return False
        self._save()
        return True

    def _renumber(self, flow: Flow):
        for i, s in enumerate(flow.steps):
            s.position = i

    # ---------- denormalize ----------
    def project_onto(self, bookmarks_by_id: Dict[int, Bookmark]) -> None:
        """Stamp each bookmark with its flow_id and flow_position fields."""
        # Reset existing stamps
        for bm in bookmarks_by_id.values():
            bm.flow_id = ""
            bm.flow_position = 0
        for flow in self._flows.values():
            for step in flow.steps:
                bm = bookmarks_by_id.get(step.bookmark_id)
                if bm is None:
                    continue
                bm.flow_id = flow.id
                bm.flow_position = step.position
