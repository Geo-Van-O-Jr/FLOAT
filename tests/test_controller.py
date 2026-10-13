from collections import deque
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PySide6.QtCore import QObject
from float_app import app as module
from float_app.app import Controller
from float_app.commands import Command, CommandParser
from float_app.config import Settings
from float_app.speech_logic import Utterance
from float_app.state import Session


@pytest.fixture
def control(monkeypatch):
    controller = Controller.__new__(Controller)
    QObject.__init__(controller)
    controller.session = Session()
    controller.settings = Settings(configured=True)
    controller.executor = Mock()
    controller.engine = Mock()
    controller.speech = Mock()
    controller.speech.submit.return_value = True
    controller.window = SimpleNamespace(feedback=Mock())
    controller.parser = CommandParser()
    controller.ready = {"dictation": True, "voice": True}
    controller.quitting = False
    controller.dictation_has_text = False
    controller.voice_latency = deque()
    controller.dictation_latency = deque()
    monkeypatch.setattr(module, "foreground", lambda: 42)
    return controller


def test_pending_dictation_never_types_after_pause(control):
    snapshot = control.session.transition("dictation", 42)
    job = Utterance(b"", snapshot, 42, 0)
    control.pause()
    control.transcribed(job, "Frase atrasada.", 1200)
    control.executor.text.assert_not_called()
    control.executor.release_all.assert_called_once()


def test_pending_dictation_never_types_in_other_window(control, monkeypatch):
    snapshot = control.session.transition("dictation", 42)
    job = Utterance(b"", snapshot, 42, 0)
    monkeypatch.setattr(module, "foreground", lambda: 99)
    control.transcribed(job, "Frase para a janela original.", 1200)
    control.executor.text.assert_not_called()
    assert control.session.snapshot().mode == "dictation_suspended"


def test_dictation_commands_and_unknown_addressed_text_are_not_inserted(control):
    snapshot = control.session.transition("dictation", 42)
    job = Utterance(b"", snapshot, 42, 0)
    control.transcribed(job, "Computador, comando desconhecido.", 1200)
    control.executor.text.assert_not_called()
    control.transcribed(job, "Computador, pausar.", 1200)
    control.executor.text.assert_not_called()
    assert control.session.snapshot().mode == "paused"


def test_dictation_preserves_accents_and_phrase_separation(control):
    snapshot = control.session.transition("dictation", 42)
    job = Utterance(b"", snapshot, 42, 0)
    control.transcribed(job, "Ação e atenção.", 1200)
    control.transcribed(job, "Próxima frase.", 1200)
    assert [call.args[0] for call in control.executor.text.call_args_list] == ["Ação e atenção.", " Próxima frase."]


def test_finish_dictation_waits_behind_pending_phrase(control):
    snapshot = control.session.transition("dictation", 42)
    job = Utterance(b"", snapshot, 42, 0, Command("end_dictation"), True)
    control.heard(job)
    control.speech.submit.assert_called_once_with(job)
    assert control.session.snapshot().mode == "dictation"
    control.transcribed(job, "", 1000)
    assert control.session.snapshot().mode == "active"


def test_end_dictation_cannot_bypass_paused_setup(control):
    control.settings.configured = False
    control.execute(Command("end_dictation"))
    assert control.session.snapshot().mode == "paused"


def test_queued_audio_from_old_mode_is_ignored(control):
    snapshot = control.session.snapshot()
    control.session.transition("active")
    control.heard(Utterance(b"", snapshot, 42, 0, Command("click", "left"), True))
    control.executor.click.assert_not_called()

