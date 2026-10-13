from __future__ import annotations

import argparse
import ctypes
import logging
import os
import sys
import time
from collections import deque
from logging.handlers import RotatingFileHandler

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ.setdefault("OMP_NUM_THREADS", "4")

from PySide6.QtCore import QObject, QTimer, QLockFile, QAbstractNativeEventFilter, Signal
from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox
from .commands import Command, CommandParser
from .config import Settings, data_dir
from .gestures import GestureEngine
from .state import Session
from .windows import InputExecutor, foreground, screen_size, dpi_awareness, launch_app, set_startup, user32
from .workers import CameraWorker, AudioWorker, DictationWorker
from .ui import SettingsWindow, Overlay, app_icon

MODES = {"paused": "PAUSADO", "active": "CONTROLE ATIVO", "dictation": "DITANDO", "dictation_suspended": "DITADO SUSPENSO"}


class EmergencyHotkey(QAbstractNativeEventFilter):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback
        self.identifier = 0x464C
        self.registered = bool(user32.RegisterHotKey(None, self.identifier, 0x4000 | 0x0002 | 0x0001, ord("P")))

    def nativeEventFilter(self, event_type, message):
        from ctypes import wintypes
        msg = wintypes.MSG.from_address(int(message))
        if msg.message == 0x0312 and msg.wParam == self.identifier:
            self.callback()
            return True, 0
        return False, 0

    def close(self):
        if self.registered:
            user32.UnregisterHotKey(None, self.identifier)


class Controller(QObject):
    def __init__(self, app: QApplication, settings: Settings, background: bool = False):
        super().__init__()
        self.app, self.settings = app, settings
        self.session = Session()
        self.executor = InputExecutor()
        self.parser = CommandParser(settings.applications)
        self.engine = GestureEngine(settings.gesture, *screen_size())
        self.window = SettingsWindow(settings)
        self.overlay = Overlay()
        self.camera = self.audio = None
        self.retiring = []
        self.device_generation = 0
        self.last_frame_sequence = 0
        self.last_preview = 0.0
        self.ready = {"camera": False, "voice": False, "dictation": False}
        self.notice = "Diga “computador, ativar”" if settings.configured else "Conclua a configuração inicial"
        self.transcribing = False
        self.quitting = False
        self.pointer_latency = deque(maxlen=300)
        self.voice_latency = deque(maxlen=100)
        self.dictation_latency = deque(maxlen=100)
        self.dictation_has_text = False
        self.window.saved.connect(self.save_settings)
        self.window.toggle.connect(self.toggle)
        self.window.retry.connect(self.restart_devices)
        self.window.quit_requested.connect(self.shutdown)
        self.speech = DictationWorker(self.session)
        self.speech.health.connect(self.health)
        self.speech.result.connect(self.transcribed)
        self.speech.busy.connect(self.set_busy)
        self.speech.start()
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip("FLOAT • mãos e voz • processamento local")
        menu = QMenu()
        menu.addAction("Abrir configurações", self.show_settings)
        menu.addAction("Ativar controle", lambda: self.execute(Command("activate")))
        menu.addAction("Pausar controle", self.pause)
        menu.addSeparator()
        menu.addAction("Encerrar FLOAT", self.shutdown)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_settings() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self.tray.show()
        self.hotkey = EmergencyHotkey(self.pause)
        app.installNativeEventFilter(self.hotkey)
        self.timer = QTimer(self)
        self.timer.setInterval(16)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.restart_timer = QTimer(self)
        self.restart_timer.setInterval(100)
        self.restart_timer.timeout.connect(self.finish_restart)
        self.restart_devices()
        self.overlay.setVisible(settings.overlay)
        if not background or not settings.configured:
            self.window.show()

    def show_settings(self):
        if self.session.snapshot().mode in ("dictation", "dictation_suspended"):
            self.transition("active", "Ditado encerrado para abrir as configurações")
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def tell(self, text):
        self.notice = text
        self.window.feedback.setText(text)

    def transition(self, mode, message, target=0):
        self.session.transition(mode, target)
        self.engine.reset()
        self.executor.release_all()
        self.speech.clear()
        self.dictation_has_text = False
        self.tell(message)

    def pause(self):
        self.transition("paused", "Pausado • diga “computador, retomar”")

    def toggle(self):
        if self.session.snapshot().mode == "paused":
            self.execute(Command("activate"))
        else:
            self.pause()

    def set_busy(self, value):
        self.transcribing = value

    def health(self, component, message, ok):
        self.ready[component] = ok
        label = {"camera": self.window.camera_status, "voice": self.window.voice_status, "dictation": self.window.dictation_status}[component]
        label.setText(message)
        logging.info("component=%s ready=%s", component, ok)
        if ok and all(self.ready.values()) and self.session.snapshot().mode == "paused":
            self.tell("Diga “computador, ativar”" if self.settings.configured else "Dispositivos prontos. Calibre a área e salve a configuração.")
        if not ok:
            if component == "camera":
                self.engine.reset()
                self.executor.release_all()
                self.window.preview.frame = None
                self.window.preview.update()
            if component == "voice" and self.session.snapshot().mode != "paused":
                self.pause()
            if component == "dictation" and self.session.snapshot().mode in ("dictation", "dictation_suspended"):
                self.pause()
            self.tell(message)

    def save_settings(self, settings):
        try:
            # Startup registration is performed only after the user completes setup.
            settings.validate()
            set_startup(settings.startup)
            settings.save()
            self.settings = settings
            self.window.settings = settings
            self.parser = CommandParser(settings.applications)
            self.engine = GestureEngine(settings.gesture, *screen_size())
            self.overlay.setVisible(settings.overlay)
            self.restart_devices()
            self.tell("Configuração salva. Aguarde os dispositivos e diga “computador, ativar”.")
        except Exception as exc:
            QMessageBox.warning(self.window, "Não foi possível salvar", str(exc))

    def restart_devices(self):
        if self.quitting or self.restart_timer.isActive():
            return
        self.transition("paused", "Reconectando câmera e microfone…")
        self.device_generation += 1
        self.retiring = [worker for worker in (self.camera, self.audio) if worker is not None]
        for worker in self.retiring:
            worker.stop()
        self.ready["camera"] = self.ready["voice"] = False
        self.restart_timer.start()
        self.finish_restart()

    def finish_restart(self):
        if self.quitting or any(worker.isRunning() for worker in self.retiring):
            return
        self.restart_timer.stop()
        self.retiring = []
        token = self.device_generation
        self.camera = CameraWorker(self.settings)
        self.audio = AudioWorker(self.settings, self.session, self.parser)
        for worker in (self.camera, self.audio):
            worker.health.connect(lambda component, message, ok, generation=token: self.health(component, message, ok) if generation == self.device_generation and not self.quitting else None)
        self.audio.utterance.connect(lambda utterance, generation=token: self.heard(utterance) if generation == self.device_generation and not self.quitting else None)
        self.audio.level.connect(lambda level: self.window.meter.setValue(round(level * 100)))
        self.audio.overflow.connect(lambda: self.audio_overflow())
        self.last_frame_sequence = 0
        self.camera.start()
        self.audio.start()
        if not self.speech.isRunning() and not self.ready["dictation"]:
            self.speech.start()

    def audio_overflow(self):
        self.pause()
        self.tell("Áudio sobrecarregado. Faça uma pausa e diga “computador, retomar”.")

    def heard(self, utterance):
        if not self.session.accepts(utterance.snapshot):
            return
        command = utterance.command
        mode = self.session.snapshot().mode
        urgent = {"pause", "quit", "settings", "activate", "dictate", "continue_dictation"}
        if command and (command.kind in urgent or mode != "dictation"):
            self.voice_latency.append((time.monotonic() - utterance.ended_at) * 1000)
            self.execute(command)
        elif mode == "dictation":
            if utterance.addressed and command is None:
                self.tell("Comando não reconhecido. Repita após “computador”.")
                return
            if utterance.target != self.session.snapshot().target:
                self.suspend_dictation()
                return
            if not self.speech.submit(utterance):
                self.transition("dictation_suspended", "Ditado ocupado. Aguarde e diga “computador, continuar ditado”.")
        elif utterance.addressed:
            self.tell("Comando não reconhecido. Veja as frases na aba Guia.")

    def suspend_dictation(self):
        self.transition("dictation_suspended", "Janela mudou • diga “computador, continuar ditado”")

    def transcribed(self, utterance, text, latency_ms):
        if self.quitting or not self.session.accepts(utterance.snapshot):
            return
        state = self.session.snapshot()
        if state.mode != "dictation" or foreground() != state.target or utterance.target != state.target:
            self.suspend_dictation()
            return
        command = utterance.command or self.parser.parse(text)
        if command:
            self.execute(command)
            return
        if self.parser.is_addressed(text):
            self.tell("Comando não reconhecido; ele não foi inserido no texto.")
            return
        if text:
            try:
                self.executor.text((" " if self.dictation_has_text else "") + text)
                self.dictation_has_text = True
                self.dictation_latency.append(latency_ms)
                self.tell(f"Frase inserida • {latency_ms / 1000:.1f} s")
            except Exception as exc:
                self.suspend_dictation()
                self.tell(str(exc))

    def execute(self, command: Command):
        state = self.session.snapshot()
        try:
            if command.kind == "pause":
                self.pause()
            elif command.kind == "quit":
                self.shutdown()
            elif command.kind == "settings":
                self.show_settings()
            elif command.kind == "activate":
                if not self.settings.configured:
                    self.tell("Salve a configuração inicial antes de ativar.")
                    return
                self.transition("active", "Controle ativo • indicador para apontar")
            elif command.kind in ("dictate", "continue_dictation"):
                if not self.settings.configured:
                    self.tell("Salve a configuração inicial antes de ditar.")
                    return
                if not self.ready["dictation"] or not self.ready["voice"]:
                    self.tell("Aguarde o microfone e o ditado ficarem prontos.")
                    return
                target = foreground()
                if not target:
                    self.tell("Clique no campo em que deseja escrever.")
                    return
                self.transition("dictation", "Ditado ativo • fale e faça uma breve pausa", target)
            elif command.kind == "end_dictation":
                if state.mode in ("dictation", "dictation_suspended"):
                    self.transition("active", "Ditado encerrado • controle ativo")
                else:
                    self.tell("Não há ditado ativo.")
            elif state.mode == "paused":
                self.tell("Diga “computador, ativar” para usar os comandos.")
            else:
                # Voice pointer actions cancel a held gesture before acting.
                self.executor.release_all()
                self.engine.reset()
                if command.kind == "click":
                    self.executor.click(command.value)
                elif command.kind == "double_click":
                    self.executor.click(count=2)
                elif command.kind == "scroll":
                    self.executor.scroll(int(command.value))
                elif command.kind == "key":
                    self.executor.key(command.value)
                    if command.value in ("enter", "shift+enter", "ctrl+a", "ctrl+backspace", "ctrl+z"):
                        self.dictation_has_text = False
                elif command.kind == "text":
                    self.executor.text(command.value)
                elif command.kind == "window":
                    self.executor.window(command.value)
                elif command.kind in ("app", "custom_app"):
                    launch_app(command.value, custom=command.kind == "custom_app")
                self.tell("Comando executado")
        except Exception as exc:
            self.pause()
            self.tell(str(exc))

    def tick(self):
        if self.quitting:
            return
        now = time.monotonic()
        if self.session.focus_changed(foreground()):
            self.engine.reset()
            self.executor.release_all()
            self.speech.clear()
            self.tell("Janela mudou • diga “computador, continuar ditado”")
        state = self.session.snapshot()
        frame = self.camera.latest() if self.camera else None
        live = frame is not None and now - frame.captured_at < 0.25 and self.ready["camera"]
        try:
            if state.mode in ("active", "dictation", "dictation_suspended"):
                actions = []
                if live and frame.sequence != self.last_frame_sequence:
                    self.last_frame_sequence = frame.sequence
                    actions = self.engine.update(frame.hand, frame.captured_at)
                elif not live:
                    actions = self.engine.update(None, now)
                for action in actions:
                    if action.kind == "move":
                        self.executor.move(action.value)
                        self.pointer_latency.append((time.monotonic() - frame.captured_at) * 1000)
                    elif action.kind == "down":
                        self.executor.button(action.value, True)
                    elif action.kind == "up":
                        self.executor.button(action.value, False)
                    elif action.kind == "click":
                        self.executor.click(action.value)
                    elif action.kind == "scroll":
                        self.executor.scroll(action.value)
        except Exception as exc:
            self.pause()
            self.tell(str(exc))
        if self.window.isVisible() and now - self.last_preview > 0.1:
            self.window.preview.frame = frame if live else None
            self.window.preview.update()
            self.last_preview = now
            if live:
                self.window.metrics.setText(f"{self.engine.label}  ·  Reconhecimento: {frame.inference_ms:.0f} ms")
        label = MODES[self.session.snapshot().mode]
        self.window.status.setText(label + "  ·  " + ("Transcrevendo sua frase…" if self.transcribing else self.notice))
        self.window.toggle_button.setText("Ativar controle" if self.session.snapshot().mode == "paused" else "Pausar controle")
        self.overlay.mode.setText("FLOAT  ·  " + label)
        self.overlay.detail.setText("Transcrevendo…" if self.transcribing and state.mode == "dictation" else self.notice)
        self.overlay.gesture.setText(self.engine.label if live and state.mode != "paused" else "Processamento local • sem gravação")

    def shutdown(self):
        if self.quitting:
            return
        self.quitting = True
        self.transition("paused", "Encerrando…")
        self.timer.stop()
        self.restart_timer.stop()
        self.hotkey.close()
        self.tray.hide()
        self.overlay.hide()
        self.window.hide()
        workers = {worker for worker in (self.camera, self.audio, self.speech, *self.retiring) if worker is not None}
        for worker in workers:
            worker.stop()
        # Keep Qt alive until native inference/capture releases its resources.
        self.shutdown_timer = QTimer(self)
        self.shutdown_timer.setInterval(100)
        def finished():
            if not any(worker.isRunning() for worker in workers):
                self.executor.release_all()
                self.shutdown_timer.stop()
                self.app.quit()
        self.shutdown_timer.timeout.connect(finished)
        self.shutdown_timer.start()


def main():
    arguments = argparse.ArgumentParser(description="FLOAT — mãos e voz")
    arguments.add_argument("--background", action="store_true")
    arguments.add_argument("--self-test", metavar="REPORT")
    arguments.add_argument("--probe-devices", action="store_true")
    options = arguments.parse_args()
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))
    if options.self_test:
        from .diagnostics import self_test
        return self_test(options.self_test, options.probe_devices)
    dpi_awareness()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("FLOAT")
    app.setOrganizationName("FLOAT")
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)
    data_dir().mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(data_dir() / "float.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(None, "FLOAT", "O FLOAT já está aberto. Use o ícone na bandeja do Windows.")
        return 0
    handler = RotatingFileHandler(data_dir() / "diagnostics.log", maxBytes=100_000, backupCount=2, encoding="utf-8")
    logging.basicConfig(level=logging.WARNING, handlers=[handler])
    settings_error = ""
    try:
        settings = Settings.load()
    except (ValueError, TypeError, OSError) as exc:
        settings = Settings()
        settings_error = "Não foi possível ler a configuração. Revise os ajustes e salve novamente."
    controller = Controller(app, settings, options.background)
    if settings.configured and getattr(sys, "frozen", False):
        try:
            set_startup(settings.startup)
        except OSError:
            controller.tell("Não foi possível atualizar a inicialização automática. Salve novamente a configuração.")
    if settings_error:
        controller.tell(settings_error)
    def exception_hook(kind, value, traceback):
        logging.error("unhandled_exception=%s", kind.__name__)
        controller.pause()
        controller.tell("Ocorreu um erro. O controle foi pausado; reinicie os dispositivos.")
    sys.excepthook = exception_hook
    try:
        return app.exec()
    finally:
        controller.executor.release_all()
        lock.unlock()


if __name__ == "__main__":
    raise SystemExit(main())

