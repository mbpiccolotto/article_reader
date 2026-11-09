"""Crossref de informações (RIS)."""

from __future__ import annotations

import html
import json
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from difflib import SequenceMatcher
from pathlib import Path

from .files import ler_texto
from .models import Autor, Metadados


_RE_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>{}|\\^`\]]+)", re.IGNORECASE)


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()

def limpar_doi(doi: str) -> str:
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi.strip(), flags=re.IGNORECASE)
    return doi.rstrip(".,;)]}>").lower()

def dois_no_texto(texto: str) -> list[str]:
    vistos: list[str] = []
    for bruto in _RE_DOI.findall(texto):
        doi = limpar_doi(bruto)
        if doi not in vistos:
            vistos.append(doi)
    return vistos


# RIS
def metadados_do_texto(inicio_md: str, nome: str) -> Metadados:
    """Último recurso: primeiro título Markdown longo do início do texto, ou o nome do arquivo."""
    titulo = ""
    for linha in inicio_md.splitlines()[:80]:
        m = re.match(r"^#{1,3}\s+(.{20,300})$", linha.strip())
        if m:
            candidato = re.sub(r"[*_#]|<[^>]+>", "", m.group(1)).strip()
            if len(candidato.split()) >= 4:
                titulo = candidato
                break
    return Metadados(titulo=titulo or titulo_do_arquivo(nome), fonte="pdf")

def ler_ris(caminho: Path) -> list[Metadados]:
    if Path(caminho).is_dir():
        raise RuntimeError(f"o caminho do RIS é uma pasta, não um arquivo: {caminho}")
    texto = ler_texto(caminho, encoding="utf-8-sig", errors="replace")
    registros: list[Metadados] = []
    atual: dict[str, list[str]] = {}
    for linha in texto.splitlines():
        m = re.match(r"^([A-Z][A-Z0-9])  - ?(.*)$", linha)
        if not m:
            if atual and linha.strip() and "AB" in atual and not linha.startswith(("TY", "ER")):
                atual["AB"][-1] += " " + linha.strip()
            continue
        tag, valor = m.group(1), m.group(2).strip()
        if tag == "TY":
            atual = {}
        if tag == "ER":
            if atual:
                registros.append(_registro_para_metadados(atual))
            atual = {}
            continue
        atual.setdefault(tag, []).append(valor)
    return registros

def _primeiro(reg: dict, *tags: str) -> str:
    for tag in tags:
        if reg.get(tag) and reg[tag][0]:
            return reg[tag][0]
    return ""

def _registro_para_metadados(reg: dict) -> Metadados:
    autores = []
    for bruto in reg.get("AU", []) + ([] if reg.get("AU") else reg.get("A1", [])):
        if "," in bruto:
            sobrenome, prenomes = bruto.split(",", 1)
        else:
            partes = bruto.split()
            sobrenome, prenomes = (partes[-1], " ".join(partes[:-1])) if partes else (bruto, "")
        autores.append(Autor(sobrenome.strip(), prenomes.strip()))
    ano = re.search(r"(?:19|20)\d{2}", _primeiro(reg, "PY", "Y1", "DA"))
    resumo = _primeiro(reg, "AB", "N2")
    resumo = re.sub(r"\s*©.*$", "", resumo).strip()  # remove nota de copyright do Scopus
    return Metadados(
        autores=autores,
        ano=ano.group(0) if ano else "",
        titulo=_primeiro(reg, "TI", "T1"),
        periodico=_primeiro(reg, "T2", "JO", "JF", "JA"),
        volume=_primeiro(reg, "VL"),
        numero=_primeiro(reg, "IS"),
        pagina_inicial=_primeiro(reg, "SP"),
        pagina_final=_primeiro(reg, "EP"),
        doi=limpar_doi(_primeiro(reg, "DO")),
        palavras_chave=list(dict.fromkeys(k.strip() for k in reg.get("KW", []) if k.strip())),
        resumo=resumo,
        fonte="ris",
    )

def titulo_do_arquivo(nome: str) -> str:
    stem = Path(nome).stem
    stem = re.sub(r"^\d+[_\-\s.]+", "", stem)          # "012_Título" -> "Título"
    stem = re.sub(r"[_\s]*(OCR|ocr)$", "", stem)
    return stem

def associar_ris(arquivos: dict[str, str], registros: list[Metadados]) -> dict[str, tuple[Metadados, float]]:
    """arquivos: {nome_pdf: início do texto}. Devolve {nome_pdf: (registro, confiança)}."""
    pares: list[tuple[float, str, int]] = []
    por_doi = {r.doi: i for i, r in enumerate(registros) if r.doi}
    titulos = [normalizar(r.titulo) for r in registros]
    for nome, inicio in arquivos.items():
        for doi in dois_no_texto(inicio)[:6]:
            if doi in por_doi:
                pares.append((2.0, nome, por_doi[doi]))
        alvo = normalizar(titulo_do_arquivo(nome))
        if not alvo:
            continue
        for i, titulo in enumerate(titulos):
            comparado = titulo[: len(alvo) + 5] if len(titulo) > len(alvo) else titulo
            s = SequenceMatcher(None, alvo, comparado).ratio()
            if s >= 0.8:
                pares.append((s, nome, i))
    resultado: dict[str, tuple[Metadados, float]] = {}
    usados: set[int] = set()
    for confianca, nome, i in sorted(pares, key=lambda p: -p[0]):
        if nome in resultado or i in usados:
            continue
        resultado[nome] = (registros[i], min(confianca, 1.0))
        usados.add(i)
    return resultado
    """Último recurso: título do primeiro título Markdown ou do nome do arquivo."""
    titulo = ""
    for linha in inicio_md.splitlines()[:80]:
        m = re.match(r"^#{1,3}\s+(.{20,300})$", linha.strip())
        if m:
            candidato = re.sub(r"[*_#]|<[^>]+>", "", m.group(1)).strip()
            if len(candidato.split()) >= 4:
                titulo = candidato
                break
    return Metadados(titulo=titulo or titulo_do_arquivo(nome), fonte="pdf")