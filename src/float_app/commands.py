from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]", " ", text).strip()


def words(text: str) -> str:
    return " ".join(normalize(text).split())


@dataclass(frozen=True)
class Command:
    kind: str
    value: str = ""


PHRASES: dict[str, Command] = {}
SPOKEN: dict[str, str] = {}


def add(kind: str, value: str, *phrases: str) -> None:
    for phrase in phrases:
        PHRASES[words(phrase)] = Command(kind, value)
        SPOKEN[words(phrase)] = phrase.casefold()


add("activate", "", "ativar", "retomar", "ativar controle", "retomar controle")
add("pause", "", "pausar", "pausar controle", "parar")
add("settings", "", "abrir configurações", "configurações")
add("quit", "", "encerrar float", "encerrar controle", "encerrar aplicativo")
add("dictate", "", "iniciar ditado", "ditar")
add("end_dictation", "", "terminar ditado", "parar ditado")
add("continue_dictation", "", "continuar ditado")
add("click", "left", "clicar", "clique", "clique esquerdo")
add("click", "right", "clique direito", "clicar com botão direito")
add("double_click", "", "clique duplo", "duplo clique")
add("scroll", "-3", "rolar para baixo", "descer página")
add("scroll", "3", "rolar para cima", "subir página")
add("window", "minimize", "minimizar", "minimizar janela")
add("window", "maximize", "maximizar", "maximizar janela")
add("window", "restore", "restaurar janela")
add("key", "alt+tab", "alternar janela", "alternar janelas", "trocar janela")
add("key", "alt+f4", "fechar janela")
add("key", "ctrl+c", "copiar")
add("key", "ctrl+v", "colar")
add("key", "ctrl+x", "recortar")
add("key", "ctrl+a", "selecionar tudo")
add("key", "ctrl+z", "desfazer")
add("key", "ctrl+y", "refazer")
add("key", "ctrl+backspace", "apagar última palavra", "apagar palavra")
for spoken, key in {"enter": "enter", "tab": "tab", "escape": "esc", "espaço": "space", "apagar": "backspace", "delete": "delete", "início": "home", "fim": "end", "seta acima": "up", "seta abaixo": "down", "seta esquerda": "left", "seta direita": "right"}.items():
    add("key", key, spoken, "tecla " + spoken)
add("key", "shift+enter", "nova linha")
add("key", "tab", "próximo campo", "avançar campo", "tabulação")
add("key", "delete", "excluir")
for spoken, character in {"vírgula": ",", "ponto": ".", "ponto final": ".", "dois pontos": ":", "ponto e vírgula": ";", "interrogação": "?", "exclamação": "!"}.items():
    add("text", character, spoken)
for alias, app in {"navegador": "browser", "explorador": "explorer", "explorador de arquivos": "explorer", "bloco de notas": "notepad", "calculadora": "calculator"}.items():
    add("app", app, "abrir " + alias)


class CommandParser:
    def __init__(self, applications: dict[str, str] | None = None):
        self.phrases = dict(PHRASES)
        self.spoken = dict(SPOKEN)
        for alias, path in (applications or {}).items():
            normalized = words(alias)
            if not normalized or "abrir " + normalized in PHRASES:
                raise ValueError(f"Nome de aplicativo vazio ou reservado: {alias}")
            if "abrir " + normalized in self.phrases:
                raise ValueError(f"Nome de aplicativo repetido: {alias}")
            self.phrases["abrir " + normalized] = Command("custom_app", path)
            self.spoken["abrir " + normalized] = "abrir " + alias.casefold().strip()

    def is_addressed(self, text: str) -> bool:
        return words(text).split(" ", 1)[0] == "computador"

    def parse(self, text: str) -> Command | None:
        normalized = words(text)
        if not normalized.startswith("computador "):
            return None
        return self.phrases.get(normalized[len("computador "):])

    def grammar(self) -> list[str]:
        # The bundled small pt model has no English tokens "tab" or "delete".
        return ["computador " + phrase for phrase in self.spoken.values() if not set(phrase.split()) & {"tab", "delete", "float"}] + ["[unk]"]

