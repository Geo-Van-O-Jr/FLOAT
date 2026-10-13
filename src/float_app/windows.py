from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import winreg
from ctypes import wintypes as w
from pathlib import Path


user32 = ctypes.WinDLL("user32", use_last_error=True)
ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("mouseData", w.DWORD), ("dwFlags", w.DWORD), ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD), ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", w.DWORD), ("wParamL", w.WORD), ("wParamH", w.WORD)]


class INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", w.DWORD), ("u", INPUTUNION)]


user32.SendInput.argtypes = (w.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = w.UINT
user32.GetForegroundWindow.restype = w.HWND
user32.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
user32.SetCursorPos.restype = w.BOOL
user32.ShowWindow.argtypes = (w.HWND, ctypes.c_int)
user32.GetWindowThreadProcessId.argtypes = (w.HWND, ctypes.POINTER(w.DWORD))
user32.GetWindowThreadProcessId.restype = w.DWORD


def dpi_awareness() -> None:
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = (ctypes.c_void_p,)
        user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except AttributeError:
        user32.SetProcessDPIAware()


def foreground() -> int:
    return int(user32.GetForegroundWindow() or 0)


def own_window(hwnd: int) -> bool:
    pid = w.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value == os.getpid()


def screen_size() -> tuple[int, int]:
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


def microphone_privacy_blocked() -> bool:
    for hive, suffix in ((winreg.HKEY_CURRENT_USER, r"\NonPackaged"), (winreg.HKEY_CURRENT_USER, ""), (winreg.HKEY_LOCAL_MACHINE, "")):
        try:
            with winreg.OpenKey(hive, r"Software\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone" + suffix) as key:
                if winreg.QueryValueEx(key, "Value")[0] == "Deny":
                    return True
        except OSError:
            pass
    return False


KEYS = {"ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B, "tab": 9, "enter": 13, "esc": 27, "space": 32, "backspace": 8, "delete": 46, "home": 36, "end": 35, "left": 37, "up": 38, "right": 39, "down": 40, "f4": 0x73}
EXTENDED = {"delete", "home", "end", "left", "up", "right", "down", "win"}
BUTTONS = {"left": (0x0002, 0x0004), "right": (0x0008, 0x0010)}


class InputExecutor:
    def __init__(self):
        self.held: set[str] = set()

    def send(self, inputs: list[INPUT]) -> None:
        if not inputs:
            return
        array = (INPUT * len(inputs))(*inputs)
        sent = user32.SendInput(len(array), array, ctypes.sizeof(INPUT))
        if sent != len(array):
            raise OSError("O Windows não aceitou a entrada. Verifique se a janela exige administrador.")

    def move(self, point: tuple[int, int]) -> None:
        if not user32.SetCursorPos(*point):
            raise OSError("Não foi possível mover o ponteiro.")

    def button(self, name: str, down: bool) -> None:
        flag = BUTTONS[name][0 if down else 1]
        if down:
            self.held.add(name)
        self.send([INPUT(type=0, mi=MOUSEINPUT(dwFlags=flag))])
        if not down:
            self.held.discard(name)

    def click(self, name: str = "left", count: int = 1) -> None:
        # One batch preserves OS double-click timing, including a busy UI thread.
        items = []
        for _ in range(count):
            items.extend([INPUT(type=0, mi=MOUSEINPUT(dwFlags=flag)) for flag in BUTTONS[name]])
        self.held.add(name)
        self.send(items)
        self.held.discard(name)

    def scroll(self, ticks: int) -> None:
        self.send([INPUT(type=0, mi=MOUSEINPUT(mouseData=(ticks * 120) & 0xFFFFFFFF, dwFlags=0x0800))])

    def key(self, chord: str) -> None:
        keys = chord.split("+")
        items = []
        for release, names in ((False, keys), (True, list(reversed(keys)))):
            for name in names:
                vk = KEYS.get(name, ord(name.upper()) if len(name) == 1 else 0)
                if not vk:
                    raise ValueError("Tecla desconhecida.")
                flags = (2 if release else 0) | (1 if name in EXTENDED else 0)
                items.append(INPUT(type=1, ki=KEYBDINPUT(wVk=vk, dwFlags=flags)))
        try:
            self.send(items)
        except OSError:
            # A partial SendInput call must not strand a modifier.
            try:
                self.send(items[len(keys):])
            except OSError:
                pass
            raise

    def text(self, text: str) -> None:
        # Unicode input does not overwrite the user's clipboard and preserves accents.
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = text.split("\n")
        for line_index, line in enumerate(lines):
            if line_index:
                self.key("shift+enter")
            encoded = line.encode("utf-16-le")
            for start in range(0, len(encoded), 400):
                items = []
                chunk = encoded[start:start + 400]
                for offset in range(0, len(chunk), 2):
                    unit = int.from_bytes(chunk[offset:offset + 2], "little")
                    items.extend([INPUT(type=1, ki=KEYBDINPUT(wScan=unit, dwFlags=4)), INPUT(type=1, ki=KEYBDINPUT(wScan=unit, dwFlags=6))])
                self.send(items)

    def window(self, action: str) -> None:
        user32.ShowWindow(foreground(), {"minimize": 6, "maximize": 3, "restore": 9}[action])

    def release_all(self) -> None:
        for name in tuple(self.held):
            try:
                self.button(name, False)
            except OSError:
                pass


def default_browser() -> str:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice") as key:
            prog_id = winreg.QueryValueEx(key, "ProgId")[0]
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, prog_id + r"\shell\open\command") as key:
            command = os.path.expandvars(winreg.QueryValueEx(key, None)[0])
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        shell32.CommandLineToArgvW.argtypes = (w.LPCWSTR, ctypes.POINTER(ctypes.c_int))
        shell32.CommandLineToArgvW.restype = ctypes.POINTER(w.LPWSTR)
        argc = ctypes.c_int()
        argv = shell32.CommandLineToArgvW(command, ctypes.byref(argc))
        if argv:
            result = argv[0]
            kernel32 = ctypes.WinDLL("kernel32")
            kernel32.LocalFree.argtypes = (ctypes.c_void_p,)
            kernel32.LocalFree(argv)
            if Path(result).is_file():
                return result
    except OSError:
        pass
    raise OSError("Navegador padrão não encontrado. Cadastre seu navegador nas configurações.")


def launch_app(name: str, custom: bool = False) -> None:
    if custom:
        path = Path(name)
        if not path.is_file() or path.suffix.lower() not in (".exe", ".lnk"):
            raise OSError("O aplicativo cadastrado não foi encontrado (.exe ou .lnk).")
        os.startfile(str(path))
        return
    target = {"explorer": "explorer.exe", "notepad": "notepad.exe", "calculator": "calc.exe"}.get(name)
    if name == "browser":
        target = default_browser()
    if not target:
        raise ValueError("Aplicativo desconhecido.")
    subprocess.Popen([target], shell=False)


def startup_command() -> str:
    if getattr(sys, "frozen", False):
        return subprocess.list2cmdline([sys.executable, "--background"])
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    launcher = Path(__file__).resolve().parents[2] / "run_float.py"
    return subprocess.list2cmdline([str(pythonw), str(launcher), "--background"])


def set_startup(enabled: bool) -> None:
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
        if enabled:
            winreg.SetValueEx(key, "FLOAT", 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, "FLOAT")
            except FileNotFoundError:
                pass

