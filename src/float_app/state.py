from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class Snapshot:
    generation: int
    mode: str
    target: int


class Session:
    def __init__(self):
        self._lock = threading.Lock()
        self._state = Snapshot(0, "paused", 0)

    def snapshot(self) -> Snapshot:
        with self._lock:
            return self._state

    def transition(self, mode: str, target: int = 0) -> Snapshot:
        with self._lock:
            self._state = Snapshot(self._state.generation + 1, mode, target)
            return self._state

    def accepts(self, snapshot: Snapshot) -> bool:
        with self._lock:
            return snapshot.generation == self._state.generation

    def focus_changed(self, foreground: int) -> bool:
        with self._lock:
            if self._state.mode == "dictation" and foreground != self._state.target:
                self._state = Snapshot(self._state.generation + 1, "dictation_suspended", 0)
                return True
            return False

