"""Acesso a arquivos."""

from __future__ import annotations

import os
from pathlib import Path


# Acesso e Path
def caminho_so(caminho: Path | str) -> str:
    texto = os.path.abspath(str(caminho))
    if os.name != "nt" or texto.startswith("\\\\?\\"):
        return texto
    if texto.startswith("\\\\"):
        return "\\\\?\\UNC\\" + texto[2:]
    return "\\\\?\\" + texto

def existe(caminho: Path | str) -> bool:
    return os.path.exists(caminho_so(caminho))

def ler_bytes(caminho: Path | str) -> bytes:
    with open(caminho_so(caminho), "rb") as f:
        return f.read()

def ler_texto(caminho: Path | str, encoding: str = "utf-8", errors: str = "strict") -> str:
    with open(caminho_so(caminho), encoding=encoding, errors=errors) as f:
        return f.read()

def gravar_texto(caminho: Path | str, texto: str) -> None:
    os.makedirs(caminho_so(Path(caminho).parent), exist_ok=True)
    with open(caminho_so(caminho), "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)

def abrir_pdf(caminho: Path | str):
    import pymupdf

    return pymupdf.open(stream=ler_bytes(caminho), filetype="pdf")

def sem_prefixo(texto: str) -> str:
    if texto.startswith("\\\\?\\UNC\\"):
        return "\\\\" + texto[8:]
    if texto.startswith("\\\\?\\"):
        return texto[4:]
    return texto


# Listagem de arquivos
def listar_recursivo(pasta: Path | str, extensoes: tuple[str, ...]) -> tuple[list[Path], list[str]]:
    encontrados: list[Path] = []
    inacessiveis: list[str] = []
    for raiz, pastas, arquivos in os.walk(caminho_so(pasta), onerror=lambda e: inacessiveis.append(sem_prefixo(str(e.filename)))):
        pastas[:] = sorted(p for p in pastas if not p.startswith("."))
        for nome in sorted(arquivos):
            if nome.startswith(("~$", ".")) or not nome.lower().endswith(extensoes):
                continue
            encontrados.append(Path(sem_prefixo(os.path.join(raiz, nome))))
    return encontrados, inacessiveis
