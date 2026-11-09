"""Barra de progresso (apenas visual)"""

from __future__ import annotations

import shutil
import sys
import time

VERIFICAR = None

def _duracao(segundos: float) -> str:
    segundos = int(max(0, segundos))
    m, s = divmod(segundos, 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}min" if h else f"{m}min{s:02d}s"


class BarraProgresso:
    def __init__(self, total: int, titulo: str, largura: int = 30):
        self.total = max(total, 1)
        self.titulo = titulo
        self.largura = largura
        self.atual = 0
        self.inicio = time.time()
        self.interativo = sys.stdout.isatty()
        self._ultimo_decil = -1
        self._cheio, self._vazio = "█", "░"
        try:
            (self._cheio + self._vazio).encode(sys.stdout.encoding or "utf-8")
        except (UnicodeEncodeError, LookupError):
            self._cheio, self._vazio = "#", "-"
        self._desenhar("")

    def avancar(self, rotulo: str = "", passos: int = 1) -> None:
        if VERIFICAR:
            VERIFICAR()
        self.atual = min(self.total, self.atual + passos)
        self._desenhar(rotulo)

    def mensagem(self, texto: str) -> None:
        if self.interativo:
            sys.stdout.write("\r" + " " * (shutil.get_terminal_size((100, 20)).columns - 1) + "\r")
        print(texto, flush=True)
        self._desenhar("")

    def fim(self, resumo: str = "") -> None:
        self.atual = self.total
        self._desenhar("", final=True)
        if self.interativo:
            sys.stdout.write("\n")
        if resumo:
            print(f"  {resumo}")
        sys.stdout.flush()

    def _desenhar(self, rotulo: str, final: bool = False) -> None:
        fracao = self.atual / self.total
        decorrido = time.time() - self.inicio
        if final:
            tempo = f"em {_duracao(decorrido)}"
        elif self.atual:
            tempo = f"resta ~{_duracao(decorrido / self.atual * (self.total - self.atual))}"
        else:
            tempo = ""
        if not self.interativo:
            decil = int(fracao * 10)
            if decil != self._ultimo_decil or final:
                self._ultimo_decil = decil
                print(f"  {self.titulo}: {self.atual}/{self.total} ({fracao:.0%}) {tempo}", flush=True)
            return
        cheios = int(self.largura * fracao)
        barra = self._cheio * cheios + self._vazio * (self.largura - cheios)
        linha = f"  {self.titulo} [{barra}] {self.atual}/{self.total} {fracao:4.0%} {tempo}"
        colunas = shutil.get_terminal_size((100, 20)).columns
        espaco = colunas - len(linha) - 4
        if rotulo and espaco > 10:
            linha += "  " + (rotulo if len(rotulo) <= espaco else rotulo[: espaco - 1] + "…")
        sys.stdout.write("\r" + linha.ljust(colunas - 1)[: colunas - 1])
        sys.stdout.flush()


class Carregando:
    def __init__(self, titulo: str, largura: int = 30):
        import threading

        self.titulo = titulo
        self.largura = largura
        self.inicio = time.time()
        self.interativo = sys.stdout.isatty()
        self._parar = threading.Event()
        self._thread = threading.Thread(target=self._animar, daemon=True)
        self._cheio, self._vazio = "█", "░"
        try:
            (self._cheio + self._vazio).encode(sys.stdout.encoding or "utf-8")
        except (UnicodeEncodeError, LookupError):
            self._cheio, self._vazio = "#", "-"

    def __enter__(self):
        if VERIFICAR:
            VERIFICAR()
        if self.interativo:
            self._thread.start()
        return self

    def __exit__(self, tipo, *_):
        self._parar.set()
        if self.interativo:
            self._thread.join(timeout=1)
        if tipo is None:
            linha = f"  {self.titulo} [{self._cheio * self.largura}] concluído em {_duracao(time.time() - self.inicio)}"
            if self.interativo:
                colunas = shutil.get_terminal_size((100, 20)).columns
                sys.stdout.write("\r" + linha.ljust(colunas - 1)[: colunas - 1] + "\n")
            else:
                print(linha)
        elif self.interativo:
            sys.stdout.write("\n")
        sys.stdout.flush()
        return False

    def _animar(self):
        tamanho, pos, passo = 6, 0, 1
        colunas = shutil.get_terminal_size((100, 20)).columns
        while not self._parar.wait(0.08):
            barra = [self._vazio] * self.largura
            for i in range(pos, min(pos + tamanho, self.largura)):
                barra[i] = self._cheio
            linha = f"  {self.titulo} [{''.join(barra)}] {_duracao(time.time() - self.inicio)}"
            sys.stdout.write("\r" + linha.ljust(colunas - 1)[: colunas - 1])
            sys.stdout.flush()
            pos += passo
            if pos <= 0 or pos + tamanho >= self.largura:
                passo = -passo
