import time
import os
from pathlib import Path
from typing import Dict, Any, Set
import threading

from .config import settings
from .state_store import state_store

class FolderWatcher:
    def __init__(self):
        self.watch_dir = settings.watched_dir
        self.stabilize_seconds = settings.watcher_stabilize_seconds
        self.processed_files: Set[str] = set()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _watch_loop(self):
        while self._running:
            try:
                self.check_watched_folder()
            except Exception:
                pass
            time.sleep(2.0)

    def check_watched_folder(self):
        if not self.watch_dir.exists():
            return

        for file_path in self.watch_dir.glob("*.pdf"):
            if file_path.name in self.processed_files:
                continue

            # Check stabilization: ensure file size doesn't change
            size_initial = file_path.stat().st_size
            time.sleep(self.stabilize_seconds)
            size_current = file_path.stat().st_size

            if size_initial == size_current and size_current > 0:
                # File is stabilized! Mark processed
                self.processed_files.add(file_path.name)
                
                # Register invoice processing task
                goal = f"Process watched folder invoice document: {file_path.name}"
                task_id = state_store.create_task(
                    goal=goal,
                    workflow_id="invoice_processing",
                    context={
                        "file_path": str(file_path),
                        "filename": file_path.name,
                        "source": "watched_folder"
                    }
                )

                # Execute task in background thread
                from .agent_loop import agent_loop
                threading.Thread(target=agent_loop.run_task, args=(task_id,), daemon=True).start()

folder_watcher = FolderWatcher()
