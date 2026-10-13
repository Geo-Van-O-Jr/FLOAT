"""Recognize synthetic pt-BR fixtures; no microphone capture and no input injection."""
from __future__ import annotations

import json
import time
import wave
from pathlib import Path
import numpy as np
from vosk import Model, KaldiRecognizer, SetLogLevel
from faster_whisper import WhisperModel
from float_app.commands import CommandParser
from float_app.config import model_dir
from float_app.speech_logic import choose_command


def main():
    root = Path(__file__).resolve().parents[1]
    fixture_dir = root / ".cache" / "voice-fixtures"
    cases = json.loads((fixture_dir / "cases.json").read_text(encoding="utf-8-sig"))
    parser = CommandParser()
    SetLogLevel(-1)
    model = Model(str(model_dir() / "vosk-model-small-pt-0.3"))
    free = KaldiRecognizer(model, 16000)
    restricted = KaldiRecognizer(model, 16000, json.dumps(parser.grammar(), ensure_ascii=False))
    free.SetWords(True)
    restricted.SetWords(True)
    report = []
    for case in cases:
        with wave.open(str(fixture_dir / case["file"]), "rb") as wav:
            assert wav.getframerate() == 16000 and wav.getnchannels() == 1 and wav.getsampwidth() == 2
            pcm = wav.readframes(wav.getnframes())
        results = []
        started = time.perf_counter()
        for recognizer in (free, restricted):
            recognizer.Reset()
            recognizer.AcceptWaveform(pcm)
            decoded = json.loads(recognizer.FinalResult())
            confidence = [w["conf"] for w in decoded.get("result", [])]
            results.append((decoded.get("text", ""), sum(confidence) / max(1, len(confidence))))
        command, addressed = choose_command(parser, *results[0], *results[1])
        expected = parser.parse(case["text"])
        report.append({"fixture": case["text"], "free": results[0][0], "constrained": results[1][0], "command": command.kind if command else None, "expected": expected.kind if expected else None, "passed": command == expected, "decoding_ms": round((time.perf_counter() - started) * 1000, 1)})
    whisper = WhisperModel(str(model_dir() / "whisper-small"), device="cpu", compute_type="int8", cpu_threads=4, local_files_only=True)
    case = cases[-1]
    with wave.open(str(fixture_dir / case["file"]), "rb") as wav:
        audio = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    started = time.perf_counter()
    segments, _ = whisper.transcribe(audio, language="pt", beam_size=1, vad_filter=True, condition_on_previous_text=False)
    transcription = " ".join(segment.text.strip() for segment in segments)
    result = {"source": "Synthetic Microsoft Maria Desktop voice; not a human acceptance test", "commands": report, "dictation": {"fixture": case["text"], "result": transcription, "processing_ms": round((time.perf_counter() - started) * 1000, 1)}}
    (root / "artifacts").mkdir(exist_ok=True)
    (root / "artifacts" / "synthetic-voice-test.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

