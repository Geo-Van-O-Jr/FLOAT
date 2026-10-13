from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from .commands import Command, CommandParser
from .state import Snapshot


@dataclass(frozen=True)
class Utterance:
    pcm: bytes
    snapshot: Snapshot
    target: int
    ended_at: float
    command: Command | None = None
    addressed: bool = False


class Segmenter:
    """20 ms PCM frames: 200 ms pre-roll, 700 ms endpoint, bounded 12 s utterances."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.preroll = deque(maxlen=10)
        self.frames: list[bytes] = []
        self.voiced = 0
        self.silence = 0
        self.streak = 0
        self.active = False

    def feed(self, frame: bytes, speech: bool) -> bytes | None:
        if not self.active:
            self.preroll.append(frame)
            self.streak = self.streak + 1 if speech else 0
            if self.streak >= 3:
                self.frames = list(self.preroll)
                self.voiced = self.streak
                self.active = True
            return None
        self.frames.append(frame)
        self.voiced += int(speech)
        self.silence = 0 if speech else self.silence + 1
        if self.silence >= 35 or len(self.frames) >= 600:
            result = b"".join(self.frames) if self.voiced >= 6 else None
            self.reset()
            return result
        return None


def choose_command(parser: CommandParser, free_text: str, free_confidence: float, constrained_text: str, constrained_confidence: float) -> tuple[Command | None, bool]:
    # The open-vocabulary decoder must hear the wake word. A small command grammar
    # alone can force ordinary conversation into a plausible command.
    addressed = parser.is_addressed(free_text)
    if not addressed:
        return None, False
    direct = parser.parse(free_text)
    if direct and free_confidence >= 0.70:
        return direct, True
    candidate = parser.parse(constrained_text)
    return (candidate if constrained_confidence >= 0.78 else None), True

