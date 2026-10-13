from __future__ import annotations

import math
from dataclasses import dataclass
from .config import GestureSettings


@dataclass(frozen=True)
class HandSample:
    x: float
    y: float
    index_pinch: float
    middle_pinch: float
    index_up: bool
    middle_up: bool
    ring_up: bool = False
    little_up: bool = False


@dataclass(frozen=True)
class GestureAction:
    kind: str
    value: object = None


def from_landmarks(points) -> HandSample:
    def dist(a, b):
        return math.hypot(points[a].x - points[b].x, points[a].y - points[b].y)

    def straight(mcp, pip, dip, tip):
        ax, ay = points[mcp].x - points[pip].x, points[mcp].y - points[pip].y
        bx, by = points[tip].x - points[pip].x, points[tip].y - points[pip].y
        cosine = (ax * bx + ay * by) / max(math.hypot(ax, ay) * math.hypot(bx, by), 1e-8)
        return cosine < -0.65 and dist(0, tip) > dist(0, pip) * 1.08

    palm = max(dist(5, 17), 0.025)
    return HandSample(points[8].x, points[8].y, dist(4, 8) / palm, dist(4, 12) / palm,
                      straight(5, 6, 7, 8), straight(9, 10, 11, 12), straight(13, 14, 15, 16), straight(17, 18, 19, 20))


class GestureEngine:
    """Pure gesture state machine; time is monotonic seconds, actions contain no OS calls."""
    def __init__(self, settings: GestureSettings, width: int, height: int):
        self.settings = settings
        self.width, self.height = width, height
        self.mode = "idle"
        self.pointer: tuple[float, float] | None = None
        self.previous_time: float | None = None
        self.last_seen: float | None = None
        self.pinch_started = 0.0
        self.anchor = (0.0, 0.0)
        self.drag_offset = (0.0, 0.0)
        self.scroll_y = 0.0
        self.scroll_remainder = 0.0
        self.label = "Aguardando mão"

    def reset(self) -> list[GestureAction]:
        result = [GestureAction("up", "left")] if self.mode == "drag" else []
        self.mode = "idle"
        self.previous_time = self.last_seen = None
        self.pointer = None
        self.scroll_remainder = 0.0
        self.label = "Aguardando mão"
        return result

    def mapped(self, hand: HandSample) -> tuple[float, float]:
        x1, y1, x2, y2 = self.settings.roi
        x = ((hand.x - x1) / (x2 - x1) - 0.5) * self.settings.sensitivity + 0.5
        y = ((hand.y - y1) / (y2 - y1) - 0.5) * self.settings.sensitivity + 0.5
        return max(0, min(1, x)) * (self.width - 1), max(0, min(1, y)) * (self.height - 1)

    def move(self, target: tuple[float, float], dt: float) -> GestureAction:
        if self.pointer is None:
            self.pointer = target
        tau = 0.008 + self.settings.smoothing * 0.08
        alpha = 1 - math.exp(-max(dt, 0.001) / tau)
        self.pointer = tuple(max(0, min(limit - 1, old + alpha * (new - old))) for old, new, limit in zip(self.pointer, target, (self.width, self.height)))
        return GestureAction("move", tuple(round(v) for v in self.pointer))

    def update(self, hand: HandSample | None, now: float) -> list[GestureAction]:
        if hand is None:
            if self.last_seen is not None and now - self.last_seen >= self.settings.loss_ms / 1000:
                return self.reset()
            return []
        dt = now - self.previous_time if self.previous_time is not None else 1 / 30
        self.previous_time = self.last_seen = now
        target = self.mapped(hand)
        g = self.settings
        if self.mode in ("pinch", "drag"):
            if hand.index_pinch >= g.pinch_open:
                action = GestureAction("up", "left") if self.mode == "drag" else GestureAction("click", "left")
                self.mode = "idle"
                self.label = "Soltar" if action.kind == "up" else "Clique"
                return [action]
            if self.mode == "pinch" and now - self.pinch_started >= g.drag_ms / 1000:
                self.mode = "drag"
                self.drag_offset = self.anchor[0] - target[0], self.anchor[1] - target[1]
                self.label = "Arrastando"
                return [GestureAction("down", "left")]
            if self.mode == "drag":
                return [self.move((target[0] + self.drag_offset[0], target[1] + self.drag_offset[1]), dt)]
            return []
        if self.mode == "right_pinch":
            if hand.middle_pinch >= g.pinch_open:
                self.mode = "idle"
                self.label = "Clique direito"
                return [GestureAction("click", "right")]
            return []
        if hand.index_pinch <= g.pinch_close or hand.middle_pinch <= g.pinch_close:
            if self.pointer is None:
                # First acquire a pointing pose; a newly detected pinch must not click an unrelated location.
                self.label = "Aponte com o indicador"
                return []
            self.mode = "pinch" if hand.index_pinch <= hand.middle_pinch else "right_pinch"
            self.pinch_started = now
            self.anchor = self.pointer
            self.scroll_remainder = 0.0
            self.label = "Pinça" if self.mode == "pinch" else "Pinça direita"
            return []
        if hand.index_up and hand.middle_up and not hand.ring_up and not hand.little_up:
            if self.mode != "scroll":
                self.mode, self.scroll_y, self.scroll_remainder = "scroll", hand.y, 0.0
                self.label = "Rolando"
                return []
            delta = (self.scroll_y - hand.y) * g.scroll_gain
            self.scroll_y = hand.y
            self.scroll_remainder += delta
            ticks = math.trunc(self.scroll_remainder)
            self.scroll_remainder -= ticks
            return [GestureAction("scroll", ticks)] if ticks else []
        self.mode = "idle"
        self.scroll_remainder = 0.0
        if hand.index_up and not hand.middle_up and not hand.ring_up and not hand.little_up:
            self.label = "Apontando"
            return [self.move(target, dt)]
        self.label = "Mão em repouso"
        return []

