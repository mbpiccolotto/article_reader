"""Metadados dos artigos."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from .file_io import ler_bytes
from .models import Autor, Metadados


# DOI
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

def _titulo_candidato(inicio_md: str, evitar: frozenset[str] = frozenset()) -> str:
    for linha in inicio_md.splitlines()[:80]:
        m = re.match(r"^#{1,3}\s+(.{20,300})$", linha.strip())
        if m:
            candidato = re.sub(r"[*_#]|<[^>]+>", "", m.group(1)).strip()
            if len(candidato.split()) >= 4 and normalizar(candidato) not in evitar:
                return candidato
    return ""

def textos_parecidos(a: str, b: str, limite: float = 0.5) -> bool:
    palavras_a, palavras_b = set(normalizar(a[:6000]).split()), set(normalizar(b[:6000]).split())
    if not palavras_a or not palavras_b:
        return False
    return len(palavras_a & palavras_b) / len(palavras_a | palavras_b) >= limite

def titulos_de_cabecalho(inicios: dict[str, str]) -> frozenset[str]:
    por_titulo: dict[str, list[str]] = {}
    for inicio in inicios.values():
        titulo = normalizar(_titulo_candidato(inicio))
        if titulo:
            por_titulo.setdefault(titulo, []).append(inicio)
    return frozenset(t for t, textos in por_titulo.items()
                     if any(not textos_parecidos(textos[0], outro) for outro in textos[1:]))

def metadados_do_texto(inicio_md: str, nome: str, evitar: frozenset[str] = frozenset()) -> Metadados:
    titulo = _titulo_candidato(inicio_md, evitar)
    return Metadados(titulo=titulo or titulo_do_arquivo(nome), fonte="pdf")


# RIS
def _decodificar(dados: bytes) -> str:
    if dados.startswith((b"\xff\xfe", b"\xfe\xff")):
        return dados.decode("utf-16")
    try:
        return dados.decode("utf-8-sig")
    except UnicodeDecodeError:
        return dados.decode("cp1252", errors="replace")

_RE_TAG_RIS = re.compile(r"^\s*([A-Z][A-Z0-9])  ?-(?: (.*))?$")

def ler_ris(caminho: Path) -> list[Metadados]:
    if Path(caminho).is_dir():
        raise RuntimeError(f"o caminho do RIS é uma pasta, não um arquivo: {caminho}")
    texto = _decodificar(ler_bytes(caminho))
    registros: list[Metadados] = []
    atual: dict[str, list[str]] = {}
    ultima: str | None = None

    def guardar() -> None:
        if atual and (atual.get("TI") or atual.get("T1") or atual.get("DO")):
            registros.append(_registro_para_metadados(atual))

    for linha in texto.splitlines():
        m = _RE_TAG_RIS.match(linha)
        if not m:
            if ultima and linha.strip():
                atual[ultima][-1] = (atual[ultima][-1] + " " + linha.strip()).strip()
            continue
        tag, valor = m.group(1), (m.group(2) or "").strip()
        if tag == "TY":
            guardar()
            atual, ultima = {}, None
        if tag == "ER":
            guardar()
            atual, ultima = {}, None
            continue
        atual.setdefault(tag, []).append(valor)
        ultima = tag
    guardar()
    return registros

def _primeiro(reg: dict, *tags: str) -> str:
    for tag in tags:
        if reg.get(tag) and reg[tag][0]:
            return reg[tag][0]
    return ""

def _registro_para_metadados(reg: dict) -> Metadados:
    autores = []
    for bruto in reg.get("AU", []) + ([] if reg.get("AU") else reg.get("A1", [])):
        if not bruto.strip():
            continue
        if "," in bruto:
            sobrenome, prenomes = bruto.split(",", 1)
        else:
            partes = bruto.split()
            sobrenome, prenomes = (partes[-1], " ".join(partes[:-1])) if partes else (bruto, "")
        autores.append(Autor(sobrenome.strip(), prenomes.strip()))
    ano = re.search(r"(?:19|20)\d{2}", _primeiro(reg, "PY", "Y1", "DA"))
    resumo = _primeiro(reg, "AB", "N2")
    resumo = re.sub(r"\s*©.*$", "", resumo).strip()
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


# RIS - PDF
"""Liga cada registro RIS a um PDF."""

def titulo_do_arquivo(nome: str) -> str:
    stem = Path(nome).stem
    stem = re.sub(r"^\d+[_\-\s.]+", "", stem)
    stem = re.sub(r"[_\s]*(OCR|ocr)$", "", stem)
    return stem

def _tem_titulo(titulo_norm: str, inicio_norm: str) -> bool:
    return len(titulo_norm) >= 25 and titulo_norm in inicio_norm

def associar_ris(arquivos: dict[str, str], registros: list[Metadados]) -> dict[str, tuple[Metadados, float]]:
    pares: list[tuple[float, str, int]] = []
    por_doi = {r.doi: i for i, r in enumerate(registros) if r.doi}
    titulos = [normalizar(r.titulo) for r in registros]
    for nome, inicio in arquivos.items():
        linhas = inicio.splitlines()
        cabecalho = "\n".join(linhas[:60])
        inicio_norm = normalizar("\n".join(linhas[:120]))
        for doi in dois_no_texto(cabecalho)[:6]:
            if doi in por_doi:
                pares.append((2.0, nome, por_doi[doi]))
        for doi in dois_no_texto(inicio)[:10]:
            i = por_doi.get(doi)
            if i is not None and _tem_titulo(titulos[i], inicio_norm):
                pares.append((1.5, nome, i))
        for i, titulo in enumerate(titulos):
            if _tem_titulo(titulo, inicio_norm):
                pares.append((1.0, nome, i))
        alvo = normalizar(titulo_do_arquivo(nome))
        if not alvo:
            continue
        for i, titulo in enumerate(titulos):
            if not titulo:
                continue
            comparado = titulo[: len(alvo) + 5] if len(titulo) > len(alvo) else titulo
            comp = SequenceMatcher(None, alvo, comparado)
            if comp.real_quick_ratio() >= 0.8 and comp.quick_ratio() >= 0.8:
                similaridade = comp.ratio()
                if similaridade >= 0.8:
                    pares.append((similaridade, nome, i))
    resultado: dict[str, tuple[Metadados, float]] = {}
    usados: set[int] = set()
    for confianca, nome, i in sorted(pares, key=lambda p: -p[0]):
        if nome in resultado or i in usados:
            continue
        resultado[nome] = (registros[i], min(confianca, 1.0))
        usados.add(i)
    return resultado