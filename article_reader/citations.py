"""ABNT NBR 10520:2023 e ABNT NBR 6023:2018."""

from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from string import ascii_lowercase

from .models import Artigo, Autor


# Nomes Autores
_PARTICULAS = {"de", "da", "do", "das", "dos", "e", "van", "von", "der", "den", "del", "della", "la", "le", "di", "du"}

def _ascii(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()

def nome_em_texto(sobrenome: str) -> str:
    """'SILVA FILHO' -> 'Silva Filho'; mantém grafias mistas."""
    if not sobrenome.isupper() and not sobrenome.islower():
        return sobrenome
    partes = []
    for i, parte in enumerate(sobrenome.lower().split()):
        partes.append(parte if (i > 0 and parte in _PARTICULAS) else "-".join(p.capitalize() for p in parte.split("-")))
    return " ".join(partes)

def iniciais(prenomes: str) -> str:
    saida = []
    for nome in prenomes.replace(".", ". ").split():
        if nome in _PARTICULAS:
            continue
        partes = [p for p in nome.split("-") if p]
        saida.append("-".join(f"{p[0].upper()}." for p in partes))
    return " ".join(saida)


# Autor/Ano
def atribuir_chaves(artigos: list[Artigo]) -> None:
    usadas: set[str] = set()
    for artigo in sorted(artigos, key=lambda a: (a.metadados.titulo.lower(), a.arquivo)):
        meta = artigo.metadados
        base = re.sub(r"[^a-z]", "", _ascii(meta.autores[0].sobrenome).lower()) if meta.autores else ""
        base = (base or re.sub(r"[^a-z]", "", _ascii(meta.titulo).lower())[:10] or "artigo")[:20] + (meta.ano or "sd")
        chave, n = base, 0
        while chave in usadas:
            chave = base + ascii_lowercase[n % 26] * (n // 26 + 1)
            n += 1
        usadas.add(chave)
        artigo.chave = chave

    for artigo in artigos:
        artigo.iniciais_na_citacao = False
    por_rotulo: dict[tuple[str, str], list[Artigo]] = defaultdict(list)
    for artigo in artigos:
        por_rotulo[(_autoria_parentetica(artigo).lower(), artigo.metadados.ano)].append(artigo)
    for membros in por_rotulo.values():
        if len({_identidade(a) for a in membros}) > 1:
            for artigo in membros:
                artigo.iniciais_na_citacao = bool(artigo.metadados.autores and artigo.metadados.autores[0].prenomes)

    grupos: dict[tuple[str, str], list[Artigo]] = defaultdict(list)
    for artigo in artigos:
        grupos[(_autoria_parentetica(artigo).lower(), artigo.metadados.ano)].append(artigo)
    for (_, ano), membros in grupos.items():
        ordenados = sorted(membros, key=lambda a: a.metadados.titulo.lower())
        for letra, artigo in zip(ascii_lowercase, ordenados):
            artigo.sufixo_ano = letra if (len(membros) > 1 and ano) else ""

def _identidade(artigo: Artigo) -> tuple:
    return tuple((_ascii(a.sobrenome).lower(), iniciais(a.prenomes)) for a in artigo.metadados.autores)

def ano(artigo: Artigo) -> str:
    return (artigo.metadados.ano or "[s. d.]") + artigo.sufixo_ano

def _nomes(artigo: Artigo) -> list[str]:
    nomes = [nome_em_texto(a.sobrenome) for a in artigo.metadados.autores]
    if artigo.iniciais_na_citacao and nomes:
        nomes[0] = f"{nomes[0]}, {iniciais(artigo.metadados.autores[0].prenomes)}"
    return nomes

def _autoria_parentetica(artigo: Artigo) -> str:
    if not artigo.metadados.autores:
        primeira = (artigo.metadados.titulo.split() or ["Título"])[0]
        return f"{primeira.upper()} [...]"
    nomes = _nomes(artigo)
    return "; ".join(nomes) if len(nomes) <= 3 else f"{nomes[0]} et al."

def autoria_narrativa(artigo: Artigo) -> str:
    if not artigo.metadados.autores:
        return _autoria_parentetica(artigo)
    nomes = _nomes(artigo)
    if len(nomes) == 1:
        return nomes[0]
    if len(nomes) <= 3:
        return ", ".join(nomes[:-1]) + " e " + nomes[-1]
    return f"{nomes[0]} et al."

def plural(artigo: Artigo) -> bool:
    return len(artigo.metadados.autores) > 1

def pagina_citada(artigo: Artigo, pagina_pdf: int) -> int:
    return pagina_pdf + artigo.deslocamento_pagina


# Citações
def citacao(artigos: list[Artigo] | Artigo, pagina: int | None = None) -> str:
    """(Silva, 2020); (Silva, 2020, p. 7); (Costa et al., 2019a, 2019b; Souza; Lima, 2021)."""
    if isinstance(artigos, Artigo):
        artigos = [artigos]
    itens = sorted(artigos, key=lambda a: (_ascii(_autoria_parentetica(a)).lower(), ano(a)))
    partes: list[str] = []
    ultimo = None
    for artigo in itens:
        autoria = _autoria_parentetica(artigo)
        data = ano(artigo) + (f", p. {pagina_citada(artigo, pagina)}" if pagina and len(itens) == 1 else "")
        if autoria == ultimo:
            partes[-1] += f", {data}"
        else:
            partes.append(f"{autoria}, {data}")
        ultimo = autoria
    return "(" + "; ".join(partes) + ")"

def citacao_narrativa(artigo: Artigo, pagina: int | None = None) -> str:
    data = ano(artigo) + (f", p. {pagina_citada(artigo, pagina)}" if pagina else "")
    return f"{autoria_narrativa(artigo)} ({data})"

def _autor_referencia(autor: Autor) -> str:
    ini = iniciais(autor.prenomes)
    return f"{autor.sobrenome.upper()}, {ini}" if ini else autor.sobrenome.upper()


# Referencial
def referencia_abnt(artigo: Artigo) -> list[tuple[str, bool]]:
    """Referência como trechos (texto, negrito); o título do periódico vai em negrito."""
    meta = artigo.metadados
    trechos: list[tuple[str, bool]] = []
    if meta.autores:
        autores = meta.autores if len(meta.autores) <= 3 else meta.autores[:1]
        autoria = "; ".join(_autor_referencia(a) for a in autores)
        if len(meta.autores) > 3:
            autoria += " et al"
        trechos.append((autoria.rstrip(".") + ". ", False))
    titulo = re.sub(r"\s+", " ", meta.titulo.strip()).rstrip(".")
    if not meta.autores:
        primeira, _, resto = titulo.partition(" ")
        titulo = f"{primeira.upper()} {resto}".strip()
    trechos.append((titulo + ("" if titulo.endswith(("?", "!")) else ".") + " ", False))
    if meta.periodico:
        trechos.append((meta.periodico.strip().rstrip("."), True))
        detalhes = []
        if meta.volume:
            detalhes.append(f"v. {meta.volume}")
        if meta.numero:
            detalhes.append(f"n. {meta.numero}")
        paginas = meta.paginas.replace("--", "-").replace("–", "-")
        if paginas:
            detalhes.append(paginas if not paginas[0].isdigit() or "-" not in paginas and len(paginas) > 5 else f"p. {paginas}")
        detalhes.append(ano(artigo))
        trechos.append((", " + ", ".join(detalhes) + ".", False))
    else:
        trechos.append((ano(artigo) + ".", False))
    if meta.doi:
        trechos.append((f" DOI: https://doi.org/{meta.doi}.", False))
    return trechos

def ordenar_referencias(artigos: list[Artigo]) -> list[Artigo]:
    def chave(a: Artigo):
        entrada = referencia_abnt(a)[0][0] if a.metadados.autores else a.metadados.titulo
        return (_ascii(entrada).lower(), ano(a), _ascii(a.metadados.titulo).lower())

    return sorted(artigos, key=chave)
