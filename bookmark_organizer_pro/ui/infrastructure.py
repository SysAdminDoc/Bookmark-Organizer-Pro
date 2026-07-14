"""Small UI infrastructure helpers used by the desktop shell."""

from __future__ import annotations

import tkinter as tk
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Dict, List

from bookmark_organizer_pro.logging_config import log


# =============================================================================
# Window Transparency
# =============================================================================
class WindowTransparency:
    """Manage window transparency/opacity"""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self._opacity = 1.0
    
    @property
    def opacity(self) -> float:
        return self._opacity
    
    @opacity.setter
    def opacity(self, value: float):
        """Set window opacity (0.0 to 1.0)"""
        self._opacity = max(0.3, min(1.0, value))  # Min 30% opacity
        self.root.attributes('-alpha', self._opacity)
    
    def increase(self, step: float = 0.1):
        """Increase opacity"""
        self.opacity = self._opacity + step
    
    def decrease(self, step: float = 0.1):
        """Decrease opacity"""
        self.opacity = self._opacity - step
    
    def reset(self):
        """Reset to full opacity"""
        self.opacity = 1.0


# =============================================================================
# NON-BLOCKING TASK RUNNER
# =============================================================================
@dataclass(frozen=True)
class _DispatchEvent:
    """Immutable callback envelope produced without touching Tcl/Tk."""

    callback: Callable
    args: tuple[Any, ...]
    kwargs: tuple[tuple[str, Any], ...]


class TkEventDispatcher:
    """Deliver worker events through one poller owned by the Tk thread."""

    def __init__(self, root: tk.Misc, *, poll_interval_ms: int = 16, max_events_per_tick: int = 256):
        self.root = root
        self.poll_interval_ms = max(1, int(poll_interval_ms))
        self.max_events_per_tick = max(1, int(max_events_per_tick))
        self._events: queue.Queue[_DispatchEvent] = queue.Queue()
        self._closed = threading.Event()
        self._owner_thread = threading.get_ident()
        self._after_id = None
        setattr(root, "_bop_ui_dispatcher", self)
        self._schedule()

    @property
    def closed(self) -> bool:
        return self._closed.is_set()

    def post(self, callback: Callable, *args, **kwargs) -> bool:
        """Enqueue a callback without invoking any Tk method from the caller."""
        if self.closed:
            return False
        self._events.put(
            _DispatchEvent(
                callback=callback,
                args=tuple(args),
                kwargs=tuple(kwargs.items()),
            )
        )
        return not self.closed

    def _schedule(self) -> None:
        if self.closed:
            return
        try:
            self._after_id = self.root.after(self.poll_interval_ms, self._drain)
        except Exception:
            self._closed.set()
            self._discard_pending()

    def _drain(self) -> None:
        """Run queued callbacks on the Tk owner thread, then reschedule once."""
        self._after_id = None
        if self.closed:
            self._discard_pending()
            return
        for _index in range(self.max_events_per_tick):
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            if self.closed:
                break
            try:
                event.callback(*event.args, **dict(event.kwargs))
            except Exception:
                log.warning("Tk event callback failed", exc_info=True)
        if self.closed:
            self._discard_pending()
            return
        self._schedule()

    def _discard_pending(self) -> None:
        while True:
            try:
                self._events.get_nowait()
            except queue.Empty:
                return

    def shutdown(self) -> None:
        """Cancel polling and discard every queued or subsequently posted event."""
        if self._closed.is_set():
            return
        self._closed.set()
        after_id = self._after_id
        self._after_id = None
        if after_id is not None and threading.get_ident() == self._owner_thread:
            try:
                self.root.after_cancel(after_id)
            except Exception:
                pass
        if getattr(self.root, "_bop_ui_dispatcher", None) is self:
            try:
                delattr(self.root, "_bop_ui_dispatcher")
            except Exception:
                pass
        self._discard_pending()


class NonBlockingTaskRunner:
    """
    Runs tasks in background threads with proper UI updates.
    Ensures GUI never locks up.
    """
    
    def __init__(self, root: tk.Tk, *, dispatcher: TkEventDispatcher | None = None):
        self.root = root
        self.dispatcher = dispatcher or TkEventDispatcher(root)
        self._owns_dispatcher = dispatcher is None
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._tasks: Dict[str, Any] = {}
        self._tasks_lock = threading.Lock()
        self._stopping = threading.Event()

    def _track_future(self, task_id: str, future):
        """Remember a future while it is active, then drop it when finished."""
        with self._tasks_lock:
            self._tasks[task_id] = future

        def forget(_future):
            with self._tasks_lock:
                if self._tasks.get(task_id) is _future:
                    self._tasks.pop(task_id, None)

        future.add_done_callback(forget)
        return future
    
    def run_task(self, task_id: str, func: Callable, 
                 on_progress: Callable = None,
                 on_complete: Callable = None,
                 on_error: Callable = None,
                 *args, **kwargs):
        """
        Run a task in background thread.
        
        Args:
            task_id: Unique identifier for the task
            func: Function to run
            on_progress: Progress callback (called via after())
            on_complete: Completion callback (called via after())
            on_error: Error callback (called via after())
        """
        def wrapper():
            try:
                result = func(*args, **kwargs)
                if on_complete:
                    self.dispatcher.post(on_complete, result)
            except Exception as e:
                if on_error:
                    self.dispatcher.post(on_error, e)
        
        future = self._executor.submit(wrapper)
        return self._track_future(task_id, future)
    
    def run_with_progress(self, task_id: str, items: List,
                          process_func: Callable,
                          on_progress: Callable = None,
                          on_complete: Callable = None):
        """
        Run a task over multiple items with progress updates.
        """
        def wrapper():
            results = []
            total = len(items)
            
            for i, item in enumerate(items):
                try:
                    result = process_func(item)
                    results.append(result)
                except Exception:
                    results.append(None)
                
                if on_progress:
                    self.dispatcher.post(on_progress, i + 1, total, item)
            
            if on_complete:
                self.dispatcher.post(on_complete, results)
        
        future = self._executor.submit(wrapper)
        return self._track_future(task_id, future)
    
    def cancel(self, task_id: str):
        """Cancel a running task"""
        with self._tasks_lock:
            future = self._tasks.pop(task_id, None)
        if future is not None:
            future.cancel()
    
    def shutdown(self):
        """Shutdown the executor"""
        self._stopping.set()
        with self._tasks_lock:
            futures = list(self._tasks.values())
            self._tasks.clear()
        for future in futures:
            future.cancel()
        self._executor.shutdown(wait=False, cancel_futures=True)
        if self._owns_dispatcher:
            self.dispatcher.shutdown()
