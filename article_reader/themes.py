"""Eixos temáticos."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import normalize

from .config import Config
from .glossary import GENERICOS, METODOLOGICOS, VAGOS
from .models import Artigo, Frase

@dataclass
class Tema:
    termo: str
    rotulo: str
    traduzido: bool
    trechos: list[tuple[Artigo, Frase]] = field(default_factory=list)

    @property
    def sentidos(self) -> set[str]:
        return {f.sentido for _, f in self.trechos if f.sentido}

@dataclass
class Eixo:
    titulo: str
    termos: list[str]
    artigos: list[Artigo]
    temas: list[Tema] = field(default_factory=list)

def normalizar_termo(termo: str) -> str:
    termo = re.sub(r"\s+", " ", termo.lower().strip())
    termo = termo.replace("flavour", "flavor").replace("odour", "odor")
    return termo

def singular(termo: str) -> str:
    palavras = termo.split()
    ultima = palavras[-1]
    if re.search(r"[-–][a-z]{1,3}$|\d", ultima):  # siglas como "gc-ms", "hs-spme"
        return termo
    if len(ultima) > 4 and ultima.endswith("ies"):
        ultima = ultima[:-3] + "y"
    elif len(ultima) > 4 and ultima.endswith("s") and not ultima.endswith(("ss", "us", "is")):
        ultima = ultima[:-1]
    return " ".join(palavras[:-1] + [ultima])

def padrao_termo(termo: str) -> re.Pattern:
    palavras = singular(termo).split()
    partes = [re.escape(p).replace(r"\-", r"[-\s]?") for p in palavras]
    ultima = partes[-1]
    if ultima.endswith("y"):
        ultima = ultima[:-1] + r"(?:y|ies)"
    else:
        ultima += r"(?:s|es)?"
    return re.compile(r"\b" + r"[\s-]+".join(partes[:-1] + [ultima]) + r"\b", re.IGNORECASE)

def traduzir(termo: str, glossario: dict[str, str]) -> tuple[str, bool]:
    t = normalizar_termo(termo)
    for chave in (t, singular(t), t + "s"):
        if chave in glossario:
            return glossario[chave], True
    return termo, False

def _palavras_chave(artigo: Artigo) -> set[str]:
    return {singular(normalizar_termo(k)) for k in artigo.metadados.palavras_chave if 2 < len(k) < 60}

def construir_eixos(artigos: list[Artigo], cfg: Config, glossario: dict[str, str], log=print) -> list[Eixo]:
    if len(artigos) < max(2 * cfg.min_artigos, 6):
        eixo = Eixo("Resultados dos estudos incluídos", [], list(artigos))
        eixo.temas = construir_temas(eixo, artigos, cfg, glossario)
        return [eixo]

    textos = [_texto_tematico(a) for a in artigos]
    vetorizador = TfidfVectorizer(
        sublinear_tf=True, token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z0-9\-]{2,}\b",
    )
    X = vetorizador.fit_transform(textos)
    # LSA: reduz o vocabulário a ~20 dimensões latentes; separa melhor temas em corpora homogêneos
    dims = max(2, min(20, len(artigos) - 1, X.shape[1] - 1))
    Z = normalize(TruncatedSVD(dims, random_state=0).fit_transform(X))

    k_max = max(cfg.min_eixos, min(cfg.max_eixos, len(artigos) // cfg.min_eixos))
    melhor = None
    for k in range(cfg.min_eixos, k_max + 1):
        modelo = KMeans(n_clusters=k, n_init=50, random_state=0).fit(Z)
        if len(set(modelo.labels_)) < 2:
            continue
        nota = silhouette_score(Z, modelo.labels_, metric="cosine")
        tamanhos = sorted(Counter(modelo.labels_.tolist()).values(), reverse=True)
        log(f"    k = {k}: silhueta = {nota:.3f}; tamanhos = {tamanhos}")
        if melhor is None or nota > melhor[0]:
            melhor = (nota, k, modelo.labels_.copy())
    rotulos = melhor[2] if melhor else np.zeros(len(artigos), dtype=int)
    rotulos = _fundir_pequenos(Z, rotulos, cfg.min_artigos)

    df_corpus = Counter(t for a in artigos for t in _palavras_chave(a))
    eixos = []
    for grupo in sorted(set(rotulos), key=lambda g: -int((rotulos == g).sum())):
        membros = [a for a, r in zip(artigos, rotulos) if r == grupo]
        termos = _rotular(membros, artigos, df_corpus, X, rotulos == grupo, vetorizador, glossario)
        rotulos_pt = list(dict.fromkeys(traduzir(t, glossario)[0] for t in termos))  # "e-nose" e "electronic nose" -> um só
        titulo = _juntar(rotulos_pt) if rotulos_pt else f"Grupo temático {len(eixos) + 1}"
        eixo = Eixo(titulo[0].upper() + titulo[1:], termos, sorted(membros, key=lambda a: (a.metadados.ano, a.chave)))
        eixo.temas = construir_temas(eixo, artigos, cfg, glossario)
        eixos.append(eixo)
    return eixos

def _texto_tematico(a: Artigo) -> str:
    """O que o estudo investigou: título (peso 3), resumo e palavras-chave; sem resumo, usa os achados."""
    m = a.metadados
    partes = [m.titulo] * 3 + [m.resumo] + ["; ".join(m.palavras_chave)]
    if len(m.resumo.split()) < 50:
        partes += [f.texto for f in a.conclusoes + a.resultados]
    return " ".join(partes)

def _fundir_pequenos(Z, rotulos: np.ndarray, minimo: int) -> np.ndarray:
    rotulos = rotulos.copy()
    while True:
        tamanhos = Counter(rotulos.tolist())
        pequenos = [g for g, n in tamanhos.items() if n < minimo]
        if not pequenos or len(tamanhos) <= 1:
            return rotulos
        g = min(pequenos, key=lambda x: tamanhos[x])
        outros = [o for o in tamanhos if o != g]
        centros = {o: Z[rotulos == o].mean(axis=0) for o in outros}
        for i in np.where(rotulos == g)[0]:
            v = Z[i]
            rotulos[i] = max(outros, key=lambda o: float(v @ centros[o]) / (np.linalg.norm(centros[o]) + 1e-9))

def _rotular(membros, todos, df_corpus, X, mascara, vetorizador, glossario) -> list[str]:
    n_in, n_out = len(membros), max(len(todos) - len(membros), 1)
    textos_in = [(a.metadados.titulo + " " + a.metadados.resumo) for a in membros]
    textos_todos = [(a.metadados.titulo + " " + a.metadados.resumo) for a in todos]
    dentro = Counter(t for a in membros for t in _palavras_chave(a))
    for termo in glossario:
        t = singular(normalizar_termo(termo))
        dentro.setdefault(t, 2)  # termos do glossário entram como candidatos (verificados no texto abaixo)
    pontuados = []
    for termo, c in dentro.items():
        if c < 2 or termo in GENERICOS or termo in VAGOS or df_corpus[termo] > 0.4 * len(todos):
            continue
        padrao = padrao_termo(termo)
        no_texto = sum(1 for t in textos_in if padrao.search(t))
        if no_texto < 2:  # descarta termos de indexação automática que não aparecem no texto
            continue
        if sum(1 for t in textos_todos if padrao.search(t)) > 0.5 * len(todos):
            continue
        fora = sum(1 for t in textos_todos if padrao.search(t)) - no_texto
        nota = (no_texto / n_in) - (fora / n_out)
        if traduzir(termo, glossario)[1]:
            nota += 0.15
        elif len(termo.split()) == 1:
            nota -= 0.1
        pontuados.append((nota, c, termo))
    escolhidos: list[str] = []
    traducoes: set[str] = set()
    for _, _, termo in sorted(pontuados, reverse=True):
        rotulo = traduzir(termo, glossario)[0].lower()
        if any(termo in e or e in termo for e in escolhidos) or rotulo in traducoes:
            continue
        escolhidos.append(termo)
        traducoes.add(rotulo)
        if len(escolhidos) == 3:
            break
    if not escolhidos:  # nenhum termo reconhecível: termos TF-IDF mais característicos do grupo
        centro = np.asarray(X[mascara].mean(axis=0)).ravel() - np.asarray(X[~mascara].mean(axis=0)).ravel()
        nomes = vetorizador.get_feature_names_out()
        for i in np.argsort(-centro)[:30]:
            termo = nomes[i]
            if termo in GENERICOS or termo in VAGOS or any(termo in e or e in termo for e in escolhidos):
                continue
            escolhidos.append(termo)
            if len(escolhidos) == 2:
                break
    return escolhidos

def _juntar(itens: list[str]) -> str:
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + " e " + itens[-1]


_COBERTURA_CORPUS: dict[tuple[int, str], int] = {}


def _artigos_com_termo(termo: str, todos: list[Artigo]) -> int:
    chave = (id(todos), termo)
    if chave not in _COBERTURA_CORPUS:
        padrao = padrao_termo(termo)
        _COBERTURA_CORPUS[chave] = sum(
            1 for a in todos if any(padrao.search(f.texto) for f in a.resultados + a.candidatas + a.conclusoes)
        )
    return _COBERTURA_CORPUS[chave]

def construir_temas(eixo: Eixo, todos: list[Artigo], cfg: Config, glossario: dict[str, str]) -> list[Tema]:
    df_corpus = Counter(t for a in todos for t in _palavras_chave(a))
    candidatos: set[str] = set()
    for a in eixo.artigos:
        candidatos |= _palavras_chave(a)
    candidatos |= {singular(normalizar_termo(t)) for t in glossario if len(t) > 3}
    candidatos = {
        t for t in candidatos
        if t not in GENERICOS and t not in METODOLOGICOS and t not in {normalizar_termo(x) for x in eixo.termos}
        and df_corpus.get(t, 0) <= 0.5 * len(todos) and len(t) > 3
    }

    cobertura: dict[str, dict[str, Frase]] = {}
    for termo in candidatos:
        padrao = padrao_termo(termo)
        achados = {}
        for a in eixo.artigos:
            for f in a.resultados + a.candidatas + a.conclusoes:
                if padrao.search(f.texto):
                    achados.setdefault(a.chave, f)  # listas já ordenadas por relevância
                    break
        if len(achados) >= 2 and (len(todos) < 10 or _artigos_com_termo(termo, todos) <= 0.35 * len(todos)):
            cobertura[termo] = achados

    por_chave = {a.chave: a for a in eixo.artigos}
    temas: list[Tema] = []
    cobertos: set[str] = set()
    usadas: set[tuple[str, int]] = set()
    while len(temas) < cfg.max_temas and cobertura:
        def ganho(t):
            novos = len(set(cobertura[t]) - cobertos)
            return (novos, traduzir(t, glossario)[1], len(cobertura[t]), len(t.split()))

        termo = max(cobertura, key=ganho)
        if ganho(termo)[0] < 2 and temas:
            break
        achados = cobertura.pop(termo)
        for outro in list(cobertura):  # evita temas quase iguais ("pyrazine" e "alkylpyrazine")
            if termo in outro or outro in termo:
                cobertura.pop(outro)
        rotulo, traduzido = traduzir(termo, glossario)
        tema = Tema(termo, rotulo, traduzido)
        for chave, frase in sorted(achados.items(), key=lambda kv: (por_chave[kv[0]].metadados.ano, kv[0])):
            if (chave, frase.ordem) in usadas:
                continue
            tema.trechos.append((por_chave[chave], frase))
            usadas.add((chave, frase.ordem))
        if len(tema.trechos) >= 2:
            temas.append(tema)
            cobertos |= set(achados)
    return temas
