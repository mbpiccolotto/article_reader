"""Leitura de PDF e Markdown."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote

from .file_io import abrir_pdf, existe, ler_texto


# Constantes
"""Expressões regulares."""

RE_MARCA_PAGINA = re.compile(r"<!-- p\. (\d+) -->")
_LIGADURAS_UNICODE = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"}
_INSERCOES = ("ff", "fi", "fl", "ffi", "ffl", "ft")
_RE_LEGENDA = re.compile(r"^\s*(fig(?:ure|\.)?|figura|table|tabela|quadro|scheme|chart|gr[áa]fico)\s*\.?\s*S?\d+",
                         re.IGNORECASE)


# Resultados
class ErroLeitura(RuntimeError):
    pass

@dataclass
class Figura:
    arquivo: Path
    pagina: int
    legenda: str = ""

@dataclass
class Tabela:
    pagina: int
    linhas: list[list[str]]
    legenda: str = ""

@dataclass
class Leitura:
    texto: str
    figuras: list[Figura] = field(default_factory=list)
    tabelas: list[Tabela] = field(default_factory=list)
    ocr: bool = False


# OCR
_RE_PRODUTOR_OCR = re.compile(r"tesseract|ocrmypdf|abbyy|finereader|paper ?capture|omnipage|readiris|ocr", re.IGNORECASE)

def _tem_camada_ocr(doc) -> bool:
    meta = doc.metadata or {}
    if _RE_PRODUTOR_OCR.search(" ".join(str(meta.get(k) or "") for k in ("producer", "creator"))):
        return True
    for pagina in list(doc)[:3]:
        if any("GlyphLess" in (f[3] or "") for f in pagina.get_fonts()):
            return True
    return False

def _texto_ocr(doc) -> list[str]:
    paginas = []
    for pagina in doc:
        palavras = pagina.get_text("words")
        meio = pagina.rect.width / 2
        colunas = [palavras]
        if palavras:
            cruzam = sum(1 for w in palavras if w[0] < meio < w[2])
            esquerda = [w for w in palavras if (w[0] + w[2]) / 2 < meio]
            direita = [w for w in palavras if (w[0] + w[2]) / 2 >= meio]
            if cruzam / len(palavras) < 0.02 and min(len(esquerda), len(direita)) > 0.25 * len(palavras):
                colunas = [esquerda, direita]
        paginas.append("\n\n".join(t for t in (_linhas_em_paragrafos(c) for c in colunas) if t))
    return paginas

def _linhas_em_paragrafos(palavras: list) -> str:
    if not palavras:
        return ""
    alturas = sorted(w[3] - w[1] for w in palavras)
    altura = alturas[len(alturas) // 2] or 10
    linhas: list[list] = []
    for w in sorted(palavras, key=lambda w: ((w[1] + w[3]) / 2, w[0])):
        centro = (w[1] + w[3]) / 2
        if linhas and abs(centro - linhas[-1][0]) < altura * 0.5:
            linhas[-1][1].append(w)
        else:
            linhas.append([centro, [w]])
    paragrafos, atual, anterior = [], "", None
    for centro, ws in linhas:
        texto = " ".join(w[4] for w in sorted(ws, key=lambda w: w[0]))
        if anterior is not None and centro - anterior > altura * 1.9:
            paragrafos.append(atual)
            atual = ""
        atual = atual[:-1] + texto if atual.endswith("-") and texto[:1].islower() else f"{atual} {texto}".strip()
        anterior = centro
    paragrafos.append(atual)
    return "\n\n".join(p for p in paragrafos if p.strip())


# Texto e Espaçamento
_RE_COLADO = re.compile(r"[^\W\d_]{22,}")
_FOLGA_ESPACO = 0.10

def _texto_linha(linha: dict) -> str:
    return "".join(s.get("text", "") for s in linha["spans"])

def _refazer_espacos(linha: dict) -> None:
    anterior = None
    for trecho in linha["spans"]:
        partes = []
        for c in trecho["chars"]:
            x0, _, x1, _ = c["bbox"]
            if anterior and c["c"].strip() and anterior[1].strip() and x0 - anterior[0] > _FOLGA_ESPACO * trecho["size"]:
                partes.append(" ")
            partes.append(c["c"])
            anterior = (x1, c["c"])
        trecho["text"] = "".join(partes)

def _blocos_da_pagina(pagina, flags) -> list[dict]:
    blocos = [b for b in pagina.get_text("dict", flags=flags)["blocks"] if b.get("type") == 0]
    if not any(_RE_COLADO.search(_texto_linha(l)) for b in blocos for l in b["lines"]):
        return blocos
    brutos = [b for b in pagina.get_text("rawdict", flags=flags)["blocks"] if b.get("type") == 0]
    for bloco in brutos:
        for linha in bloco["lines"]:
            for trecho in linha["spans"]:
                trecho["text"] = "".join(c["c"] for c in trecho["chars"])
            if _RE_COLADO.search(_texto_linha(linha)):
                _refazer_espacos(linha)
    return brutos

def _ordenar_colunas(blocos: list[dict], largura: float) -> list[dict]:
    meio = largura / 2
    folga = largura * 0.03

    def largo(b):
        x0, _, x1, _ = b["bbox"]
        return x0 < meio - folga and x1 > meio + folga

    ordenados, faixa = [], []

    def esvaziar():
        esquerda = sorted((b for b in faixa if (b["bbox"][0] + b["bbox"][2]) / 2 < meio), key=lambda b: b["bbox"][1])
        direita = sorted((b for b in faixa if (b["bbox"][0] + b["bbox"][2]) / 2 >= meio), key=lambda b: b["bbox"][1])
        ordenados.extend(esquerda + direita)
        faixa.clear()

    for b in sorted(blocos, key=lambda b: (b["bbox"][1], b["bbox"][0])):
        if largo(b):
            esvaziar()
            ordenados.append(b)
        else:
            faixa.append(b)
    esvaziar()
    return ordenados


# PDF
def ler_pdf(pdf: Path, pasta_figuras: Path | None = None, *, extrair_tabelas: bool = True,
            max_figuras: int = 8, dpi_figuras: int = 150) -> Leitura:
    import pymupdf

    try:
        doc = abrir_pdf(pdf)
    except Exception as erro:
        raise ErroLeitura(f"não foi possível abrir o PDF: {erro}") from erro
    try:
        if doc.needs_pass and not doc.authenticate(""):
            raise ErroLeitura("PDF protegido por senha.")
        if _tem_camada_ocr(doc):
            paginas = _texto_ocr(doc)
            texto = "\n".join(f"\n<!-- p. {i} -->\n{_normalizar_unicode(t)}" for i, t in enumerate(paginas, 1))
            return Leitura("<!-- ocr: texto obtido por reconhecimento óptico; confira as citações -->\n" + texto,
                           _extrair_figuras(doc, pdf, pasta_figuras, [], max_figuras, dpi_figuras), [], ocr=True)
        return _ler_pdf_textual(doc, pdf, pasta_figuras, extrair_tabelas, max_figuras, dpi_figuras, pymupdf)
    except ErroLeitura:
        raise
    except Exception as erro:
        raise ErroLeitura(f"falha ao ler o PDF: {erro}") from erro
    finally:
        doc.close()

def _ler_pdf_textual(doc, pdf, pasta_figuras, extrair_tabelas, max_figuras, dpi, pymupdf) -> Leitura:
    flags = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES
    paginas, tamanhos, ocorrencias = [], Counter(), Counter()
    tabelas: list[Tabela] = []
    for num, pagina in enumerate(doc, 1):
        caixas_tab = []
        if extrair_tabelas and re.search(r"\b(tab(?:le|ela|\.)?|quadro)\s*S?\d", pagina.get_text("text"), re.IGNORECASE):
            try:
                palavras = pagina.get_text("words")
                for tab in pagina.find_tables().tables:
                    dados = [[_texto_celula(c, palavras) for c in linha.cells] for linha in tab.rows]
                    dados = [l for l in dados if any(l)]
                    if len(dados) >= 2 and len(dados[0]) >= 2:
                        caixas_tab.append(pymupdf.Rect(tab.bbox))
                        tabelas.append(Tabela(num, dados))
            except Exception:  # noqa: BLE001 — detecção de tabela é opcional
                pass
        blocos = _blocos_da_pagina(pagina, flags)
        linhas = []
        for bloco in _ordenar_colunas(blocos, pagina.rect.width):
            for linha in bloco["lines"]:
                spans = [s for s in linha["spans"] if s["text"].strip()]
                if not spans:
                    continue
                caixa = pymupdf.Rect(linha["bbox"])
                if any(caixa.intersects(r) and (caixa & r).get_area() > 0.6 * max(caixa.get_area(), 1e-6) for r in caixas_tab):
                    continue
                texto = re.sub(r"\s+", " ", "".join(s["text"] for s in linha["spans"])).strip()
                tam = max(s["size"] for s in spans)
                negrito = all((s["flags"] & 16) or "bold" in s["font"].lower() for s in spans)
                linhas.append({"texto": texto, "tam": tam, "negrito": negrito, "bloco": bloco["number"],
                               "linhas_bloco": len(bloco["lines"]), "y": caixa.y0, "y1": caixa.y1})
                tamanhos[round(tam, 1)] += len(texto)
                ocorrencias[re.sub(r"\d+", "#", texto.lower())] += 1
        paginas.append(linhas)

    corpo = tamanhos.most_common(1)[0][0] if tamanhos else 10
    n_pag = len(paginas)
    repetidas = {t for t, n in ocorrencias.items() if n_pag >= 3 and n >= max(3, 0.4 * n_pag) and len(t) < 120}

    saida: list[str] = []
    legendas: list[dict] = []
    for num, linhas in enumerate(paginas, 1):
        saida.append(f"\n<!-- p. {num} -->\n")
        paragrafo: list[str] = []
        bloco_ant = None

        def descarregar():
            if paragrafo:
                txt = ""
                for parte in paragrafo:
                    txt = txt[:-1] + parte if txt.endswith("-") and parte[:1].islower() else (txt + " " + parte).strip()
                saida.append(txt + "\n")
                paragrafo.clear()

        for ln in linhas:
            txt = ln["texto"]
            if re.sub(r"\d+", "#", txt.lower()) in repetidas:
                continue
            if _RE_LEGENDA.match(txt):
                legendas.append({"pagina": num, "legenda": txt, "y": ln["y"], "y1": ln["y1"]})
            titulo = (
                4 <= len(txt) < 120 and not txt.endswith((".", ",", ";", ":")) and not _RE_LEGENDA.match(txt)
                and re.search(r"[^\W\d_]{3}", txt)
                and (ln["tam"] >= corpo * 1.15
                     or (ln["negrito"] and ln["linhas_bloco"] == 1 and len(txt) < 80
                         and re.match(r"^(\d+(\.\d+)*\.?\s+)?[A-ZÀ-Ú]", txt)))
            )
            if titulo:
                descarregar()
                if saida and saida[-1].startswith("\n## ") and ln["bloco"] == bloco_ant:
                    saida[-1] = saida[-1].rstrip("\n") + f" {txt}\n"
                else:
                    saida.append(f"\n## {txt}\n")
            else:
                if ln["bloco"] != bloco_ant:
                    descarregar()
                paragrafo.append(txt)
            bloco_ant = ln["bloco"]
        descarregar()

    for t in tabelas:
        candidatas = [l for l in legendas if l["pagina"] == t.pagina and re.match(r"\s*(tab|quadro)", l["legenda"], re.I)]
        if candidatas:
            t.legenda = candidatas[0]["legenda"]
    texto = _normalizar_unicode(re.sub(r"\n{3,}", "\n\n", "".join(s if s.endswith("\n") else s + "\n" for s in saida)))
    if len(re.sub(r"<!--.*?-->|\s+", "", texto)) < 300:
        raise ErroLeitura("o PDF não tem texto extraível suficiente (escaneado sem OCR?).")
    figuras = _extrair_figuras(doc, pdf, pasta_figuras, legendas, max_figuras, dpi)
    return Leitura(texto, figuras, tabelas)


# Imagens e Tabelas
def _texto_celula(caixa, palavras) -> str:
    if not caixa:
        return ""
    x0, y0, x1, y1 = caixa
    dentro = [w for w in palavras if x0 <= (w[0] + w[2]) / 2 <= x1 and y0 <= (w[1] + w[3]) / 2 <= y1]
    return " ".join(w[4] for w in sorted(dentro, key=lambda w: (round(w[1]), w[0]))).strip()

def _legenda_proxima(legendas, pagina, r) -> str:
    candidatas = [l for l in legendas if l["pagina"] == pagina and not re.match(r"\s*(tab|quadro)", l["legenda"], re.I)]
    if not candidatas:
        return ""
    return min(candidatas, key=lambda l: min(abs(l["y"] - r.y1), abs(l["y1"] - r.y0)))["legenda"]

def _extrair_figuras(doc, pdf, pasta, legendas, maximo, dpi) -> list[Figura]:
    if not pasta or maximo <= 0:
        return []
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    uso_xref = Counter(x[0] for p in doc for x in p.get_images(full=True))
    figuras: list[Figura] = []
    for num, pagina in enumerate(doc, 1):
        area = pagina.rect.get_area()
        regioes = []
        for info in pagina.get_images(full=True):
            if uso_xref[info[0]] > 1:
                continue
            for r in pagina.get_image_rects(info[0]):
                regioes.append(r)
        try:
            regioes += list(pagina.cluster_drawings())
        except Exception:  # noqa: BLE001
            pass
        aceitas = []
        for r in sorted(regioes, key=lambda r: -r.get_area()):
            if r.width < 120 or r.height < 80 or r.get_area() > 0.92 * area:
                continue
            if any((r & a).get_area() > 0.5 * min(r.get_area(), a.get_area()) for a in aceitas):
                continue
            aceitas.append(r)
        for k, r in enumerate(sorted(aceitas, key=lambda r: (r.y0, r.x0)), 1):
            if len(figuras) >= maximo:
                return figuras
            destino = pasta / f"{_seguro(pdf.stem)[:60]}_p{num:02d}_{k:02d}.jpg"
            try:
                pix = pagina.get_pixmap(clip=r + (-3, -3, 3, 3), dpi=dpi)
                pix.save(destino, jpg_quality=82)
            except Exception:  # noqa: BLE001
                continue
            figuras.append(Figura(destino, num, _legenda_proxima(legendas, num, r)))
    return figuras

def _seguro(nome: str) -> str:
    return re.sub(r"[^\w\-]+", "_", unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode())


# Markdown
def ler_md(md: Path) -> Leitura:
    texto = _normalizar_unicode(ler_texto(md, encoding="utf-8-sig", errors="replace"))
    if "<!-- p. " not in texto:
        texto = "<!-- p. 1 -->\n" + texto
    figuras = []
    for alt, alvo in re.findall(r"!\[([^\]]*)\]\(<?([^)>]+?)>?(?:\s+\"[^\"]*\")?\)", texto):
        if re.match(r"[a-z][a-z0-9+.-]*://", alvo, re.IGNORECASE):
            continue
        arq = md.parent / unquote(alvo.strip())
        if existe(arq) and arq.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".bmp"):
            figuras.append(Figura(arq, 0, alt.strip()))
    return Leitura(texto, figuras[:8])

def _normalizar_unicode(texto: str) -> str:
    for lig, sub in _LIGADURAS_UNICODE.items():
        texto = texto.replace(lig, sub)
    texto = texto.replace("­", "").replace("​", "")
    return unicodedata.normalize("NFC", texto)


# Fixing
_RE_PALAVRA = re.compile(r"[A-Za-z]{2,}")
_PUA = "-"
_RE_PALAVRA_PUA = re.compile(rf"[A-Za-z{_PUA}]*[{_PUA}][A-Za-z{_PUA}]*")

class Vocabulario(Counter):
    """Em quantos documentos cada palavra aparece (`n_docs` = tamanho do corpus)."""
    n_docs: int = 0

def frequencia_documental(textos: Iterable[str]) -> Vocabulario:
    df = Vocabulario()
    for texto in textos:
        df.update({p.lower() for p in _RE_PALAVRA.findall(re.sub(rf"[A-Za-z]*[{_PUA}][A-Za-z{_PUA}]*", " ", texto))})
        df.n_docs += 1
    return df

def reparar_ligaduras(texto: str, df: Counter, total_docs: int) -> tuple[str, Counter]:
    """Recompõe palavras que perderam a ligadura na extração ("Coee" -> "Coffee")."""
    limite_raro = max(3, int(total_docs * 0.03))
    trocas: Counter = Counter()
    cache: dict[str, str | None] = {}

    def corrigir(m: re.Match) -> str:
        palavra = m.group(0)
        chave = palavra.lower()
        if chave not in cache:
            cache[chave] = _melhor_reparo(chave, df, limite_raro)
        reparo = cache[chave]
        if not reparo:
            return palavra
        trocas[f"{palavra}->{reparo}"] += 1
        if palavra.isupper():
            return reparo.upper()
        return reparo[0].upper() + reparo[1:] if palavra[0].isupper() else reparo

    def corrigir_pua(m: re.Match) -> str:
        palavra = m.group(0)
        letras = re.sub(f"[{_PUA}]", "", palavra)
        if not letras:
            return " "
        reparo = _reparar_pua(palavra, df)
        trocas[f"{letras}->{reparo}"] += 1
        return reparo

    linhas = []
    for linha in texto.split("\n"):
        if linha.startswith("<!--"):
            linhas.append(linha)
        else:
            linhas.append(_RE_PALAVRA.sub(corrigir, _RE_PALAVRA_PUA.sub(corrigir_pua, linha)))
    return "\n".join(linhas), trocas

def _reparar_pua(palavra: str, df: Counter) -> str:
    candidatos = [""]
    for ch in palavra:
        if "" <= ch <= "":
            candidatos = [c + ins for c in candidatos for ins in ("fi", "fl", "ff", "ffi", "ffl", "ft", "")][:400]
        else:
            candidatos = [c + ch for c in candidatos]
    melhor = max(candidatos, key=lambda c: (df.get(c.lower(), 0) + (1000 if c.lower() in _LEXICO_LIGADURAS else 0), -len(c)))
    conhecida = df.get(melhor.lower(), 0) > 0 or melhor.lower() in _LEXICO_LIGADURAS
    return melhor if conhecida else re.sub(f"[{_PUA}]", "", palavra)

# "Ligaduras"
_LEXICO_LIGADURAS = frozenset("""
coffee coffees effect effects effective effectively affect affected affects different differ differs difference differences
differential differentiation efficient efficiency efficiently sufficient sufficiently insufficient office offset suffer
buffer buffers staff stuff diffusion diffuse diffused diffuses afford affinity affiliation offer offered offers
field fields find finding findings finds first final finally fine finer fingerprint fingerprints finish finished
film films filter filtered filtering filters fibre fibres fiber fibers file files fill filled fit fitted fitting
profile profiles profiling specific specifically specification classified classification identified identification
quantified quantification certified modified modification verified justified simplified significant significantly
significance fluid fluids flow flows flowing flavor flavors flavour flavours flavonoid flavonoids fluorescence fluorescent
flat flame float floral flower flowers flush flux fluctuation fluctuations flexible flexibility conflict conflicts
influence influenced influences inflammation inflammatory reflect reflects reflected reflection refine refined
benefit benefits benefited confirm confirmed confirms conformation configuration definition definitions defined
define defines sacrifice artifact artifacts after often soft softer left lift lifted shift shifted shifts craft
fragrance fresh frequency frequencies fruity fully functional function functions further
aflatoxin ester esters fructose glucose fluorescein fingerprinting
café cafés eficiência eficiente diferença diferenças diferente diferentes efeito efeitos efetivo afetado afetados
filtro filtros fluxo fluxos fino final finais fibra fibras perfil perfis específico específicos especificamente
significativo significativa significativos classificação classificado identificação identificado quantificação
influência refletir benefício benefícios confirmado confirmou definição definido flavonoide flavonoides sabor
""".split())

_CURTAS_QUEBRADAS = {"rst", "nal", "eld", "uid", "ber", "lms", "ows", "lm"}
_PROTEGIDAS = {"oral", "orally", "ash", "ashes", "ashy", "ask", "asks", "asked", "lies", "lame", "owing", "ever", "ore", "ores",
               "oat", "oats", "lied", "perl", "pers", "ower", "lower", "lowers"}

def _melhor_reparo(palavra: str, df: Counter, limite_raro: int) -> str | None:
    if (len(palavra) < 4 and palavra not in _CURTAS_QUEBRADAS) or palavra in _PROTEGIDAS:
        return None
    if palavra in _LEXICO_LIGADURAS:
        return None
    melhor, melhor_df = None, 0
    for i in range(len(palavra) + 1):
        for ins in _INSERCOES:
            candidata = palavra[:i] + ins + palavra[i:]
            n = df.get(candidata, 0) + (1000 if candidata in _LEXICO_LIGADURAS else 0)
            if n > melhor_df:
                melhor, melhor_df = candidata, n
    if melhor and melhor_df >= max(5, limite_raro, 3 * df[palavra]):
        return melhor
    return None

def reparar_corpus(textos: dict, textos_referencia: list[str], log=print) -> dict:
    """Aplica o reparo de ligaduras a todos os textos (em memória)."""
    df = frequencia_documental(list(textos.values()) + textos_referencia)
    total = len(textos) + len(textos_referencia)
    trocas_total: Counter = Counter()
    novos = {}
    for chave, texto in textos.items():
        novos[chave], trocas = reparar_ligaduras(texto, df, total)
        trocas_total.update(trocas)
    if trocas_total:
        log(f"  Reparo de ligaduras: {sum(trocas_total.values())} ocorrências em {len(trocas_total)} formas "
            f"(ex.: {', '.join(list(trocas_total)[:5])}).")
    return novos


# Validação
def eh_sumario(texto: str) -> bool:
    linhas = [l for l in texto.splitlines() if l.strip() and not l.startswith("<!--")]
    if not linhas:
        return True
    pontilhadas = sum(1 for l in linhas if re.search(r"(?:\.\s?){5,}\s*\d+\s*$", l) or re.search(r"\.{5,}", l))
    return pontilhadas / len(linhas) > 0.2

def duracao(segundos: float) -> str:
    m, s = divmod(int(math.ceil(segundos)), 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}min" if h else f"{m}min{s:02d}s"
