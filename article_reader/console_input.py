"""Funcionalidades de console e pyright."""
from __future__ import annotations

import os
import sys
import threading
import time


# Funcionalidades de console
CTRL_C, CTRL_R = "\x03", "\x12"
WINDOWS = os.name == "nt"

class NovaLeitura(Exception):
    """Ctrl+R: abandona a leitura atual e volta ao menu."""

def sair(codigo: int = 0, mensagem: str = "\nEncerrado (Ctrl+C).") -> None:
    restaurar_console()
    if mensagem:
        print(mensagem, flush=True)
    os._exit(codigo)


# CMD
_modo_original = None
def preparar_console() -> None:
    global _modo_original
    if not WINDOWS:
        return
    try:
        import ctypes

        from ctypes import wintypes

        k32 = ctypes.windll.kernel32
        k32.GetStdHandle.restype = wintypes.HANDLE
        k32.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        h = k32.GetStdHandle(-10)
        modo = wintypes.DWORD()
        if k32.GetConsoleMode(h, ctypes.byref(modo)):
            _modo_original = modo.value
            k32.SetConsoleMode(h, modo.value & ~0x0001)
        os.system("")
    except Exception:  # noqa: BLE001
        pass

def restaurar_console() -> None:
    if WINDOWS and _modo_original is not None:
        try:
            import ctypes

            from ctypes import wintypes

            k32 = ctypes.windll.kernel32
            k32.GetStdHandle.restype = wintypes.HANDLE
            k32.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            k32.SetConsoleMode(k32.GetStdHandle(-10), _modo_original)
        except Exception:  # noqa: BLE001
            pass

def _getch_posix() -> str:
    import termios
    import tty

    fd = sys.stdin.fileno()
    antigo = termios.tcgetattr(fd) #type: ignore
    try:
        tty.setraw(fd) #type: ignore
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, antigo) #type: ignore


# Keyboard input
def getch() -> str:
    if not sys.stdin.isatty():
        ch = sys.stdin.read(1)
        if ch == "":
            sair(0, "")
    elif WINDOWS:
        import msvcrt

        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            msvcrt.getwch()
            return ""
    else:
        ch = _getch_posix()
    if ch == CTRL_C:
        sair()
    return ch

def escolher(opcoes: str) -> str:
    while True:
        ch = getch()
        if ch == CTRL_R:
            raise NovaLeitura
        if ch and ch.lower() in opcoes:
            print(ch, flush=True)
            return ch.lower()

def ler_linha(prompt: str, padrao: str = "") -> str:
    print(prompt + (f" [{padrao}]" if padrao else "") + ": ", end="", flush=True)
    if not sys.stdin.isatty():
        linha = sys.stdin.readline()
        if linha == "":
            sair(0, "")
        if CTRL_R in linha:
            raise NovaLeitura
        print(linha.rstrip("\n"))
        return linha.strip() or padrao
    texto = ""
    while True:
        ch = getch()
        if ch == CTRL_R:
            print()
            raise NovaLeitura
        if ch in ("\r", "\n"):
            print(flush=True)
            return texto.strip() or padrao
        if ch in ("\x08", "\x7f"):
            if texto:
                texto = texto[:-1]
                print("\b \b", end="", flush=True)
            continue
        if ch and ch.isprintable():
            texto += ch
            print(ch, end="", flush=True)


# Monitor (Tela)
class Monitor:
    def __init__(self):
        self.pedido_nova = threading.Event()
        self._parar = threading.Event()
        self._thread = None

    def __enter__(self):
        if sys.stdin.isatty():
            self._thread = threading.Thread(target=self._rodar, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc):
        self._parar.set()
        if self._thread:
            self._thread.join(timeout=0.5)
        return False

    def verificar(self) -> None:
        if self.pedido_nova.is_set():
            raise NovaLeitura

    def _rodar(self):
        if WINDOWS:
            import msvcrt

            while not self._parar.is_set():
                if msvcrt.kbhit():
                    ch = msvcrt.getche()
                    if ch == CTRL_C:
                        sair()
                    if ch == CTRL_R:
                        self.pedido_nova.set()
                        print("\n  Ctrl+R: interrompendo para uma nova leitura...", flush=True)
                else:
                    time.sleep(0.05)
            return
        import select
        import termios
        import tty

        fd = sys.stdin.fileno()
        antigo = termios.tcgetattr(fd) #type: ignore
        try:
            tty.setcbreak(fd) #type: ignore
            novo = termios.tcgetattr(fd) #type: ignore
            novo[3] &= ~termios.ISIG #type: ignore
            termios.tcsetattr(fd, termios.TCSADRAIN, novo) #type: ignore
            while not self._parar.is_set():
                if select.select([sys.stdin], [], [], 0.05)[0]:
                    ch = sys.stdin.read(1)
                    if ch == CTRL_C:
                        termios.tcsetattr(fd, termios.TCSADRAIN, antigo) #type: ignore
                        sair()
                    if ch == CTRL_R:
                        self.pedido_nova.set()
                        print("\n  Ctrl+R: interrompendo para uma nova leitura...", flush=True)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, antigo) #type: ignore