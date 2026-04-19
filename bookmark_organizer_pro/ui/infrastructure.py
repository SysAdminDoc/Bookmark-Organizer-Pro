"""Small UI infrastructure helpers used by the desktop shell."""

from __future__ import annotations

import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List


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
class NonBlockingTaskRunner:
    """
    Runs tasks in background threads with proper UI updates.
    Ensures GUI never locks up.
    """
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._tasks: Dict[str, Any] = {}

    def _track_future(self, task_id: str, future):
        """Remember a future while it is active, then drop it when finished."""
        self._tasks[task_id] = future

        def forget(_future):
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
                    self.root.after(0, lambda result=result: on_complete(result))
            except Exception as e:
                if on_error:
                    self.root.after(0, lambda error=e: on_error(error))
        
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
                except Exception as e:
                    results.append(None)
                
                if on_progress:
                    self.root.after(0, lambda i=i, item=item: on_progress(i + 1, total, item))
                
                # Small yield to prevent blocking
                time.sleep(0.01)
            
            if on_complete:
                self.root.after(0, lambda results=results: on_complete(results))
        
        future = self._executor.submit(wrapper)
        return self._track_future(task_id, future)
    
    def cancel(self, task_id: str):
        """Cancel a running task"""
        if task_id in self._tasks:
            self._tasks[task_id].cancel()
            del self._tasks[task_id]
    
    def shutdown(self):
        """Shutdown the executor"""
        self._executor.shutdown(wait=False)
