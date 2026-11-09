"""Leitura do Markdown."""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass

from .document_reader import RE_MARCA_PAGINA


# Padrões
_CATEGORIAS = [
    ("referencias", r"^(references?|referencias(bibliograficas)?|bibliograf|literaturecited|workscited)"),
    ("fim", r"(acknowledg|agradecimento|authorcontribution|creditauthor|contribuicao|funding|financiamento|"
            r"conflictsofinterest|conflictofinterest|competinginterest|declarationofcompeting|declarationofgenerative|"
            r"dataavailability|availabilityofdata|supportinginformation|supplementary|associatedcontent|"
            r"authorinformation|abbreviations|orcid|ethic|correspondence|correspondingauthor|keywords|palavraschave|"
            r"articleinfo|informedconsent|institutionalreview|appendix|apendice|notes$|^notes|disclaimer)"),
    ("conclusao", r"(conclu|finalremarks|finalconsiderations|consideracoesfinais|concludingremarks|summaryandoutlook|perspectives$)"),
    ("resultados_discussao", r"(resultsanddiscussion|resultsanddiscussions|resultadosediscussao|resultadosydiscusion|resultsdiscussion)"),
    ("resultados", r"^(results?|resultados?|findings)$|^(results?|resultados)(and|of|$)"),
    ("discussao", r"^(discussion|discussao|discusion|generaldiscussion)"),
    ("metodos", r"(materialsandmethods|materialandmethods|materiaisemetodos|materialesymetodos|^methods?$|^methodolog|"
                r"^metodolog|^metodos?$|^experimental|^materials$|^studydesign|^statisticalanalys)"),
    ("introducao", r"^(introduction|introducao|introduccion|background)"),
    ("resumo", r"^(abstract|resumo|resumen|summary|highlights|graphicalabstract)"),
]
_RE_CATEGORIAS = [(nome, re.compile(padrao)) for nome, padrao in _CATEGORIAS]
_FORTES = {"resultados", "resultados_discussao", "discussao", "conclusao"}
RE_NUMERACAO = re.compile(r"^\s*((?:\d+|[IVX]+)(?:\.\d+)*)\.?\s+")
_RE_LEGENDA = re.compile(
    r"^\s*(?:\*\*|_)*\s*(fig(?:ure|\.)?|table|tabela|figura|scheme|chart|graph)\s*\.?\s*S?\d+[A-Za-z]?\s*(?:\*\*|_)*\s*[.:|—–-]",
    re.IGNORECASE,
)
_RE_IMAGEM = re.compile(r"^\s*(!\[|\*\*==>|<img|picture \[|\[image)", re.IGNORECASE)
ABREVIACOES = {
    "al", "e.g", "i.e", "fig", "figs", "eq", "eqs", "ref", "refs", "tab", "vs", "ca", "approx", "no", "nos",
    "var", "cv", "sp", "spp", "subsp", "etc", "resp", "min", "max", "st", "dr", "prof", "vol", "pp", "p",
    "ed", "eds", "ltd", "inc", "co", "corp", "mr", "ms", "jr", "sr", "dept", "univ", "est", "aprox", "cf",
}


# Títulos e Limpeza
"""Classifica os títulos e remove a marcação Markdown."""

@dataclass
class FraseBruta:
    texto: str
    pagina: int
    categoria: str
    secao: str
    ordem: int
    cita_externa: bool

def _chave_titulo(titulo: str) -> str:
    t = unicodedata.normalize("NFKD", titulo).encode("ascii", "ignore").decode().lower()
    t = RE_NUMERACAO.sub("", t)
    return re.sub(r"[^a-z]", "", t)

def categorizar_titulo(titulo: str) -> str | None:
    chave = _chave_titulo(titulo)
    if not chave:
        return None
    for nome, padrao in _RE_CATEGORIAS:
        if padrao.search(chave):
            return nome
    return None

def limpar_marcacao(texto: str) -> tuple[str, bool]:
    cita = False

    def sup(m: re.Match) -> str:
        nonlocal cita
        conteudo = re.sub(r"<[^>]+>|\*", "", m.group(1)).strip()
        if re.fullmatch(r"[\d,\s–\-−]+", conteudo):
            cita = True
            return " [cit]"
        return conteudo

    texto = re.sub(r"<sup>(.*?)</sup>", sup, texto, flags=re.IGNORECASE | re.DOTALL)
    texto = re.sub(r"<sub>(.*?)</sub>", r"\1", texto, flags=re.IGNORECASE | re.DOTALL)
    texto = re.sub(r"<br\s*/?>", " ", texto, flags=re.IGNORECASE)
    texto = re.sub(r"<[^>]+>", "", texto)
    texto = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", texto)
    texto = re.sub(r"\[([^\]]+)\]\((?:https?|mailto|#)[^)]*\)", r"\1", texto)
    texto = re.sub(r"(\*\*|__)", "", texto)
    texto = re.sub(r"(?<![\w*])[*_](?=\S)(.+?)(?<=\S)[*_](?![\w*])", r"\1", texto)
    texto = html.unescape(texto).replace("■", "")
    texto = re.sub(r"(?:(?<=\s)|^)_+(?=\w)|(?<=\w)_+(?=\s|$|[.,;:])", "", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto, cita

def _eh_titulo(linha: str) -> str | None:
    s = linha.strip()
    if s.startswith("#"):
        return re.sub(r"^#+\s*", "", s)

    m = re.fullmatch(r"\*\*(.{3,90}?)\*\*\s*", s)
    if m and not m.group(1).rstrip().endswith((".", ":", ";", ",")):
        texto, _ = limpar_marcacao(m.group(1))
        if categorizar_titulo(texto) or RE_NUMERACAO.match(texto):
            return m.group(1)

    texto, _ = limpar_marcacao(s)
    if 0 < len(texto.split()) <= 6 and not texto.endswith((".", ",", ";")) and categorizar_titulo(texto):
        return texto
    return None


# Leitura
def ler_markdown(md: str) -> tuple[list[FraseBruta], list[str]]:
    pagina = 1
    categoria = "pre"
    secao = ""
    numero_categoria: dict[str, str] = {}
    referencias_iniciadas = False
    paragrafos: list[tuple[str, int, str, str]] = []
    buffer: list[str] = []
    pagina_buffer = 1
    categorias_vistas: list[str] = []

    def fechar():
        nonlocal buffer
        if buffer:
            paragrafos.append((" ".join(buffer), pagina_buffer, categoria, secao))
            buffer = []

    for linha in md.splitlines():
        marca = RE_MARCA_PAGINA.search(linha)
        if marca:
            pagina = int(marca.group(1))
            continue
        if linha.startswith("<!--"):
            continue
        titulo_md = _eh_titulo(linha)
        if titulo_md is not None:
            fechar()
            titulo, _ = limpar_marcacao(titulo_md)
            nova = categorizar_titulo(titulo)
            numero = RE_NUMERACAO.match(titulo)
            topo = numero.group(1).split(".")[0] if numero else None
            if referencias_iniciadas and nova not in _FORTES:
                nova = "referencias"
            if nova:
                categoria = nova
                if topo:
                    numero_categoria[topo] = nova
                if nova == "referencias":
                    referencias_iniciadas = True
            elif topo and numero and topo in numero_categoria and "." in numero.group(1):
                categoria = numero_categoria[topo]
            elif topo and numero and "." not in numero.group(1) and categoria not in ("referencias", "fim"):
                categoria = "desenvolvimento"
                numero_categoria[topo] = categoria
            secao = titulo
            if categoria not in categorias_vistas:
                categorias_vistas.append(categoria)
            continue
        s = linha.strip()
        if not s:
            fechar()
            continue
        if s.startswith("|") or _RE_IMAGEM.match(s) or _RE_LEGENDA.match(s) or s.startswith("```"):
            fechar()
            continue
        if categoria not in categorias_vistas:
            categorias_vistas.append(categoria)
        if not buffer:
            pagina_buffer = pagina
        buffer.append(s)
    fechar()

    paragrafos = _unir_continuacoes(paragrafos)
    frases: list[FraseBruta] = []
    for texto_md, pag, cat, sec in paragrafos:
        texto, cita_sup = limpar_marcacao(texto_md)
        if len(texto.split()) < 6:
            continue
        for frase in dividir_frases(texto):
            frases.append(FraseBruta(frase, pag, cat, sec, len(frases), cita_sup and "[cit]" in frase))
    return frases, categorias_vistas

def _unir_continuacoes(paragrafos):
    unidos = []
    for p in paragrafos:
        if unidos:
            ant = unidos[-1]
            if (ant[2] == p[2] and not re.search(r"[.!?:]\W*$", ant[0].rstrip("* _"))
                    and re.match(r"^[\W_]*[a-z(]", p[0])):
                unidos[-1] = (ant[0] + " " + p[0], ant[1], ant[2], ant[3])
                continue
        unidos.append(p)
    return unidos


# Divisão
"""Divide parágrafos em frases."""

_RE_FIM_FRASE = re.compile(r"([.!?])(['\"”’)\]]*)\s+(?=[\"“'(\[]?[A-Z0-9α-ωΑ-Ω])")

def dividir_frases(texto: str) -> list[str]:
    frases, inicio = [], 0
    for m in _RE_FIM_FRASE.finditer(texto):
        anterior = texto[inicio:m.start() + 1]
        palavra = re.search(r"(\S+)\.$", anterior)
        if m.group(1) == "." and palavra:
            token = palavra.group(1).lower().strip("([")
            if token in ABREVIACOES or re.fullmatch(r"[a-z]", token) or re.fullmatch(r"[A-Z]", palavra.group(1)):
                continue
            if re.fullmatch(r"\d+", token) and re.match(r"\s*\d", texto[m.end():]):
                continue
        frases.append(texto[inicio:m.end()].strip())
        inicio = m.end()
    resto = texto[inicio:].strip()
    if resto:
        frases.append(resto)
    return frases
