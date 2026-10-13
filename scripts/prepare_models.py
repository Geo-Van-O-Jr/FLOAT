"""Download runtime models once. The application never performs these downloads."""
from __future__ import annotations

import hashlib
import json
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "models"
CACHE = ROOT / ".cache"


def download(url: str, destination: Path) -> None:
    if destination.exists():
        print(f"Já disponível: {destination.name}", flush=True)
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".partial")
    print(f"Baixando: {destination.name}", flush=True)
    urllib.request.urlretrieve(url, partial)
    partial.replace(destination)


def main():
    MODELS.mkdir(exist_ok=True)
    download("https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task", MODELS / "hand_landmarker.task")
    vosk_path = MODELS / "vosk-model-small-pt-0.3"
    if not (vosk_path / "final.mdl").exists():
        archive = CACHE / "vosk-model-small-pt-0.3.zip"
        download("https://alphacephei.com/vosk/models/vosk-model-small-pt-0.3.zip", archive)
        with zipfile.ZipFile(archive) as source:
            for item in source.infolist():
                target = (MODELS / item.filename).resolve()
                if not target.is_relative_to(MODELS.resolve()):
                    raise ValueError("Caminho inválido no pacote de modelo.")
            source.extractall(MODELS)
    print("Preparando Whisper small multilíngue…", flush=True)
    from huggingface_hub import snapshot_download
    snapshot_download("Systran/faster-whisper-small", local_dir=MODELS / "whisper-small", allow_patterns=["config.json", "model.bin", "tokenizer.json", "vocabulary.*", "preprocessor_config.json"])
    manifest = {}
    for path in sorted(MODELS.rglob("*")):
        if path.is_file() and ".cache" not in path.parts and path.name != "manifest.json":
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            manifest[path.relative_to(MODELS).as_posix()] = {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}
    (MODELS / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Modelos prontos: {len(manifest)} arquivos.", flush=True)


if __name__ == "__main__":
    main()

