from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


def data_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "FLOAT"


def model_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "models"
    return Path(__file__).resolve().parents[2] / "models"


@dataclass
class GestureSettings:
    hand: str = "Right"
    roi: list[float] = field(default_factory=lambda: [0.15, 0.15, 0.85, 0.85])
    sensitivity: float = 1.0
    smoothing: float = 0.35
    pinch_close: float = 0.38
    pinch_open: float = 0.55
    drag_ms: int = 350
    loss_ms: int = 250
    scroll_gain: float = 24.0


@dataclass
class Settings:
    schema_version: int = 1
    configured: bool = False
    camera_index: int = 0
    microphone_name: str = ""
    startup: bool = True
    overlay: bool = True
    gesture: GestureSettings = field(default_factory=GestureSettings)
    applications: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        g = self.gesture
        if g.hand not in ("Right", "Left"):
            raise ValueError("Selecione a mão direita ou esquerda.")
        if len(g.roi) != 4 or not (0 <= g.roi[0] < g.roi[2] <= 1 and 0 <= g.roi[1] < g.roi[3] <= 1):
            raise ValueError("Área da câmera inválida.")
        if g.roi[2] - g.roi[0] < 0.15 or g.roi[3] - g.roi[1] < 0.15:
            raise ValueError("A área de movimento deve ocupar pelo menos 15% da imagem.")
        if not (0.4 <= g.sensitivity <= 2.0 and 0 <= g.smoothing <= 0.9):
            raise ValueError("Sensibilidade ou suavização inválida.")
        if not (0.1 <= g.pinch_close < g.pinch_open <= 1.2 and 200 <= g.drag_ms <= 900 and 100 <= g.loss_ms <= 1000):
            raise ValueError("Limiares de gesto inválidos.")
        if not 0 <= self.camera_index <= 20:
            raise ValueError("Índice da câmera inválido.")
        if not isinstance(self.applications, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in self.applications.items()):
            raise ValueError("Cadastro de aplicativos inválido.")

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or data_dir() / "settings.json"
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("schema_version", 1) != 1:
            raise ValueError("Configuração de outra versão do FLOAT.")
        known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
        gesture = known.pop("gesture", {})
        result = cls(**known, gesture=GestureSettings(**{k: v for k, v in gesture.items() if k in GestureSettings.__dataclass_fields__}))
        result.validate()
        return result

    def save(self, path: Path | None = None) -> None:
        self.validate()
        path = path or data_dir() / "settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)

