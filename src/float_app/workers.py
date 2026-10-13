from __future__ import annotations

import json
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal
from .commands import CommandParser
from .config import Settings, model_dir
from .gestures import HandSample, from_landmarks
from .speech_logic import Segmenter, Utterance, choose_command
from .state import Session


class Worker(QThread):
    health = Signal(str, str, bool)

    def __init__(self):
        super().__init__()
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()


@dataclass
class CameraFrame:
    sequence: int
    captured_at: float
    image: object
    hand: HandSample | None
    points: object
    inference_ms: float


class CameraWorker(Worker):
    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings
        self.lock = threading.Lock()
        self.frame: CameraFrame | None = None

    def latest(self) -> CameraFrame | None:
        with self.lock:
            return self.frame

    def run(self):
        capture = None
        try:
            import cv2
            import mediapipe as mp
            from mediapipe.tasks.python import vision
            asset = model_dir() / "hand_landmarker.task"
            if not asset.exists():
                raise FileNotFoundError("Modelo das mãos ausente. Use o pacote completo do FLOAT.")
            options = vision.HandLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(asset)),
                running_mode=vision.RunningMode.VIDEO,
                num_hands=2, min_hand_detection_confidence=0.65,
                min_hand_presence_confidence=0.65, min_tracking_confidence=0.60,
            )
            with vision.HandLandmarker.create_from_options(options) as detector:
                capture = cv2.VideoCapture(self.settings.camera_index, cv2.CAP_DSHOW)
                if not capture.isOpened():
                    raise OSError("Câmera indisponível. Confira a permissão ou outro aplicativo usando a webcam.")
                capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                capture.set(cv2.CAP_PROP_FPS, 30)
                self.health.emit("camera", "Câmera conectada", True)
                sequence = 0
                previous_stamp = 0
                while not self.stop_event.is_set():
                    ok, image = capture.read()
                    captured = time.monotonic()
                    if not ok:
                        raise OSError("A câmera foi desconectada. Reconecte e use Reiniciar dispositivos.")
                    image = cv2.cvtColor(cv2.flip(image, 1), cv2.COLOR_BGR2RGB)
                    stamp = max(previous_stamp + 1, int(captured * 1000))
                    previous_stamp = stamp
                    result = detector.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=image), stamp)
                    points = None
                    for landmarks, handedness in zip(result.hand_landmarks, result.handedness):
                        if handedness[0].category_name == self.settings.gesture.hand:
                            points = landmarks
                            break
                    hand = from_landmarks(points) if points else None
                    sequence += 1
                    frame = CameraFrame(sequence, captured, image, hand, points, (time.monotonic() - captured) * 1000)
                    with self.lock:
                        self.frame = frame
        except Exception as exc:
            self.health.emit("camera", str(exc), False)
        finally:
            if capture is not None:
                capture.release()
            with self.lock:
                self.frame = None


def microphones() -> list[tuple[str, str]]:
    import sounddevice as sd
    hosts = sd.query_hostapis()
    result = []
    for index, device in enumerate(sd.query_devices()):
        if device["max_input_channels"] > 0:
            stable = f"{hosts[device['hostapi']]['name']} | {device['name']}"
            result.append((stable, stable))
    return result


def microphone_index(name: str):
    if not name:
        return None
    import sounddevice as sd
    hosts = sd.query_hostapis()
    for index, device in enumerate(sd.query_devices()):
        if device["max_input_channels"] > 0 and f"{hosts[device['hostapi']]['name']} | {device['name']}" == name:
            return index
    raise OSError("Microfone selecionado não encontrado. Selecione outro nas configurações.")


class AudioWorker(Worker):
    utterance = Signal(object)
    level = Signal(float)
    overflow = Signal()

    def __init__(self, settings: Settings, session: Session, parser: CommandParser):
        super().__init__()
        self.settings, self.session, self.parser = settings, session, parser

    def run(self):
        try:
            import numpy as np
            import sounddevice as sd
            import webrtcvad
            from vosk import Model, KaldiRecognizer, SetLogLevel
            from .windows import foreground, microphone_privacy_blocked
        except Exception as exc:
            self.health.emit("voice", str(exc), False)
            return
        packets = queue.Queue(maxsize=150)
        dropped = threading.Event()

        def callback(indata, frames, time_info, status):
            if status.input_overflow:
                dropped.set()
            try:
                packets.put_nowait((bytes(indata), self.session.snapshot(), time.monotonic()))
            except queue.Full:
                dropped.set()

        def decode(recognizer, pcm):
            recognizer.Reset()
            results = []
            for offset in range(0, len(pcm), 8000):
                if recognizer.AcceptWaveform(pcm[offset:offset + 8000]):
                    results.append(json.loads(recognizer.Result()))
            results.append(json.loads(recognizer.FinalResult()))
            text = " ".join(item.get("text", "") for item in results).strip()
            confidence = [word.get("conf", 0) for item in results for word in item.get("result", [])]
            return text, sum(confidence) / len(confidence) if confidence else 0

        try:
            if microphone_privacy_blocked():
                raise OSError("O Windows bloqueia o microfone para aplicativos de desktop. Ative o acesso em Configurações → Privacidade e segurança → Microfone e reinicie os dispositivos.")
            asset = model_dir() / "vosk-model-small-pt-0.3"
            if not (asset / "final.mdl").exists():
                raise FileNotFoundError("Modelo dos comandos ausente. Use o pacote completo do FLOAT.")
            self.health.emit("voice", "Preparando comandos de voz…", False)
            SetLogLevel(-1)
            model = Model(str(asset))
            free = KaldiRecognizer(model, 16000)
            constrained = KaldiRecognizer(model, 16000, json.dumps(self.parser.grammar(), ensure_ascii=False))
            free.SetWords(True)
            constrained.SetWords(True)
            selected = microphone_index(self.settings.microphone_name)
            rate = 16000
            try:
                sd.check_input_settings(device=selected, channels=1, dtype="int16", samplerate=rate)
            except sd.PortAudioError:
                rate = int(sd.query_devices(selected, "input")["default_samplerate"])
                sd.check_input_settings(device=selected, channels=1, dtype="int16", samplerate=rate)
            vad = webrtcvad.Vad(2)
            segmenter = Segmenter()
            snapshot = self.session.snapshot()
            target = 0
            last_voice = time.monotonic()
            count = 0
            with sd.RawInputStream(samplerate=rate, blocksize=rate // 50, device=selected, channels=1, dtype="int16", callback=callback) as stream:
                self.health.emit("voice", "Microfone conectado • diga “computador, ativar”", True)
                last_packet = time.monotonic()
                while not self.stop_event.is_set():
                    try:
                        frame, captured_state, captured_at = packets.get(timeout=0.1)
                        last_packet = time.monotonic()
                    except queue.Empty:
                        if not stream.active or time.monotonic() - last_packet > 2:
                            raise OSError("O microfone parou de responder. Use Reiniciar dispositivos.")
                        continue
                    if not self.session.accepts(captured_state):
                        segmenter.reset()
                        continue
                    if dropped.is_set():
                        dropped.clear()
                        segmenter.reset()
                        while not packets.empty():
                            try:
                                packets.get_nowait()
                            except queue.Empty:
                                break
                        self.overflow.emit()
                        continue
                    if rate != 16000:
                        # Each device packet is exactly 20 ms. Band-limited resampling
                        # is provided by libswresample through the bundled PyAV library.
                        import av
                        if not hasattr(self, "_resampler"):
                            self._resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
                            self._resampled = bytearray()
                        samples = np.frombuffer(frame, dtype=np.int16).reshape(1, -1)
                        af = av.AudioFrame.from_ndarray(samples, format="s16", layout="mono")
                        af.sample_rate = rate
                        for out in self._resampler.resample(af):
                            self._resampled.extend(out.to_ndarray().tobytes())
                        if len(self._resampled) < 640:
                            continue
                        frame = bytes(self._resampled[:640])
                        del self._resampled[:640]
                    current = self.session.snapshot()
                    if current.generation != snapshot.generation:
                        segmenter.reset()
                        snapshot = current
                    voiced = vad.is_speech(frame, 16000)
                    now = captured_at
                    if voiced:
                        last_voice = now
                    was_active = segmenter.active
                    pcm = segmenter.feed(frame, voiced)
                    if not was_active and segmenter.active:
                        snapshot, target = self.session.snapshot(), foreground()
                    count += 1
                    if count % 5 == 0:
                        rms = float(np.sqrt(np.mean(np.frombuffer(frame, dtype=np.int16).astype(np.float32) ** 2))) / 32768
                        self.level.emit(min(1.0, rms * 8))
                    if pcm:
                        free_text, free_conf = decode(free, pcm)
                        grammar_text, grammar_conf = decode(constrained, pcm)
                        command, addressed = choose_command(self.parser, free_text, free_conf, grammar_text, grammar_conf)
                        self.utterance.emit(Utterance(pcm, snapshot, target, last_voice, command, addressed))
        except Exception as exc:
            self.health.emit("voice", str(exc), False)


class DictationWorker(Worker):
    result = Signal(object, str, float)
    busy = Signal(bool)

    def __init__(self, session: Session):
        super().__init__()
        self.session = session
        self.jobs = queue.Queue(maxsize=3)
        self.ready = False

    def submit(self, utterance: Utterance) -> bool:
        try:
            self.jobs.put_nowait(utterance)
            return True
        except queue.Full:
            return False

    def clear(self):
        while True:
            try:
                self.jobs.get_nowait()
            except queue.Empty:
                return

    def run(self):
        try:
            import numpy as np
            from faster_whisper import WhisperModel
            asset = model_dir() / "whisper-small"
            if not (asset / "model.bin").exists():
                raise FileNotFoundError("Modelo do ditado ausente. Use o pacote completo do FLOAT.")
            self.health.emit("dictation", "Preparando ditado…", False)
            model = WhisperModel(str(asset), device="cpu", compute_type="int8", cpu_threads=4, num_workers=1, local_files_only=True)
            self.ready = True
            self.health.emit("dictation", "Ditado pronto • português, processamento local", True)
            while not self.stop_event.is_set():
                try:
                    job = self.jobs.get(timeout=0.1)
                except queue.Empty:
                    continue
                if not self.session.accepts(job.snapshot):
                    continue
                self.busy.emit(True)
                try:
                    if job.command is not None:
                        text = ""
                    else:
                        audio = np.frombuffer(job.pcm, dtype=np.int16).astype(np.float32) / 32768.0
                        segments, _ = model.transcribe(audio, language="pt", beam_size=1, best_of=1,
                                                      temperature=0, condition_on_previous_text=False,
                                                      vad_filter=True, vad_parameters={"min_silence_duration_ms": 500})
                        text = " ".join(segment.text.strip() for segment in segments).strip()
                    if self.session.accepts(job.snapshot) and not self.stop_event.is_set():
                        self.result.emit(job, text, (time.monotonic() - job.ended_at) * 1000)
                finally:
                    self.busy.emit(False)
        except Exception as exc:
            self.ready = False
            self.health.emit("dictation", str(exc), False)

