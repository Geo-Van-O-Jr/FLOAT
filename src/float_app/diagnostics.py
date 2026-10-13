from __future__ import annotations

import ctypes
import json
import statistics
import sys
import time
from pathlib import Path

from .config import model_dir


def self_test(report_path: str, probe_devices: bool = False) -> int:
    """Loads every packaged model offline; never injects input or stores sensor data."""
    result = {"ok": False, "network": "Python socket connections and DNS denied during this check", "checks": {}, "errors": []}

    def forbid_network(event, args):
        if event in ("socket.connect", "socket.getaddrinfo"):
            raise RuntimeError("Network is disabled for FLOAT self-test")
    sys.addaudithook(forbid_network)
    try:
        import numpy as np
        import cv2
        import sounddevice as sd
        import webrtcvad
        from vosk import Model, KaldiRecognizer, SetLogLevel
        from faster_whisper import WhisperModel
        import mediapipe as mp
        from mediapipe.tasks.python import vision
        from PySide6.QtCore import qVersion
        from .windows import INPUT
        result["checks"]["qt"] = qVersion()
        assert ctypes.sizeof(INPUT) == 40, "Invalid Win64 INPUT layout"
        result["checks"]["win64_input_layout"] = True
        root = model_dir()
        assert webrtcvad.Vad(2).is_speech(bytes(640), 16000) is False
        result["checks"]["silent_frame_vad"] = True
        options = vision.HandLandmarkerOptions(base_options=mp.tasks.BaseOptions(model_asset_path=str(root / "hand_landmarker.task")), running_mode=vision.RunningMode.VIDEO, num_hands=1)
        with vision.HandLandmarker.create_from_options(options) as hands:
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.zeros((480, 640, 3), dtype=np.uint8))
            times = []
            for index in range(10):
                started = time.perf_counter()
                detected = hands.detect_for_video(image, (index + 1) * 33)
                assert not detected.hand_landmarks
                times.append((time.perf_counter() - started) * 1000)
            result["checks"]["hand_model_blank_frames"] = {"frames": 10, "median_inference_ms": round(statistics.median(times[1:]), 1)}
            if probe_devices:
                capture = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                try:
                    if not capture.isOpened():
                        raise OSError("Webcam unavailable")
                    capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    times = []
                    for index in range(30):
                        ok, frame = capture.read()
                        if not ok:
                            raise OSError("Webcam stopped delivering frames")
                        started = time.perf_counter()
                        rgb = cv2.cvtColor(cv2.flip(frame, 1), cv2.COLOR_BGR2RGB)
                        hands.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), 1000 + index * 100)
                        times.append((time.perf_counter() - started) * 1000)
                    result["checks"]["webcam"] = {"frames": 30, "width": frame.shape[1], "height": frame.shape[0], "median_inference_ms": round(statistics.median(times), 1), "p95_inference_ms": round(sorted(times)[28], 1), "note": "Inference only, not end-to-end pointer latency"}
                finally:
                    capture.release()
        SetLogLevel(-1)
        recognizer = KaldiRecognizer(Model(str(root / "vosk-model-small-pt-0.3")), 16000)
        recognizer.AcceptWaveform(bytes(32000))
        assert json.loads(recognizer.FinalResult()).get("text", "") == ""
        result["checks"]["vosk_silence"] = True
        whisper = WhisperModel(str(root / "whisper-small"), device="cpu", compute_type="int8", cpu_threads=4, local_files_only=True)
        segments, _ = whisper.transcribe(np.zeros(16000, dtype=np.float32), language="pt", vad_filter=True)
        assert list(segments) == []
        result["checks"]["whisper_local_int8_silence"] = True
        if probe_devices:
            device = sd.query_devices(kind="input")
            rate = int(device["default_samplerate"])
            with sd.RawInputStream(samplerate=rate, channels=1, dtype="int16") as stream:
                data, overflow = stream.read(rate // 5)
                assert len(data) > 0 and not overflow
            result["checks"]["microphone"] = {"name": device["name"], "sample_rate": rate, "capture_seconds": 0.2, "saved_audio": False}
        result["ok"] = True
    except Exception as exc:
        result["errors"].append(f"{type(exc).__name__}: {exc}")
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1

