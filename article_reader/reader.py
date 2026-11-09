"""Leitura."""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .files import abrir_pdf, existe, ler_texto

RE_MARCA_PAGINA = re.compile(r"<!-- p\. (\d+) -->")
_LIGADURAS_UNICODE = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"}
_INSERCOES = ("ff", "fi", "fl", "ffi", "ffl", "ft")
_RE_LEGENDA = re.compile(r"^\s*(fig(?:ure|\.)?|figura|table|tabela|quadro|scheme|chart|gr[áa]fico)\s*\.?\s*S?\d+",
                         re.IGNORECASE)


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

# PDF
def _tem_camada_ocr(doc) -> bool:
    """PDF cujo texto vem de OCR (fonte invisível 'GlyphLessFont' do Tesseract/OCRmyPDF)."""
    for pagina in list(doc)[:3]:
        if any("GlyphLess" in (f[3] or "") for f in pagina.get_fonts()):
            return True
    return False

def _texto_ocr(doc) -> list[str]:
    """PDFs com OCR: remonta o texto pela posição das palavras, coluna por coluna."""
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

def _ordenar_colunas(blocos: list[dict], largura: float) -> list[dict]:
    """Ordem de leitura: faixas separadas por blocos de largura total; em cada faixa,
    a coluna da esquerda inteira e depois a da direita."""
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
        if extrair_tabelas and re.search(r"\b(tab(?:le|ela)|quadro)\s*S?\d", pagina.get_text("text"), re.IGNORECASE):
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
        blocos = [b for b in pagina.get_text("dict", flags=flags)["blocks"] if b.get("type") == 0]
        linhas = []
        for bloco in _ordenar_colunas(blocos, pagina.rect.width):
            for linha in bloco["lines"]:
                spans = [s for s in linha["spans"] if s["text"].strip()]
                if not spans:
                    continue
                caixa = pymupdf.Rect(linha["bbox"])
                if any(caixa.intersects(r) and (caixa & r).get_area() > 0.6 * max(caixa.get_area(), 1e-6) for r in caixas_tab):
                    continue
                texto = "".join(s["text"] for s in spans).strip()
                tam = max(s["size"] for s in spans)
                negrito = all((s["flags"] & 16) or "bold" in s["font"].lower() for s in spans)
                linhas.append({"texto": texto, "tam": tam, "negrito": negrito, "bloco": bloco["number"],
                               "y": caixa.y0, "y1": caixa.y1})
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
                len(txt) < 120 and not txt.endswith((".", ",", ";", ":")) and not _RE_LEGENDA.match(txt)
                and (ln["tam"] >= corpo * 1.15 or (ln["negrito"] and len(txt) < 80
                                                    and re.match(r"^(\d+(\.\d+)*\.?\s+)?[A-ZÀ-Ú]", txt)))
            )
            if titulo:
                descarregar()
                if saida and saida[-1].startswith("\n## ") and ln["bloco"] == bloco_ant:
                    saida[-1] = saida[-1].rstrip("\n") + f" {txt}\n"  # título em mais de uma linha
                else:
                    saida.append(f"\n## {txt}\n")
            else:
                if ln["bloco"] != bloco_ant:
                    descarregar()
                paragrafo.append(txt)
            bloco_ant = ln["bloco"]
        descarregar()

    for t in tabelas:  # legenda da tabela: a legenda "Table N" mais próxima na mesma página
        candidatas = [l for l in legendas if l["pagina"] == t.pagina and re.match(r"\s*(tab|quadro)", l["legenda"], re.I)]
        if candidatas:
            t.legenda = candidatas[0]["legenda"]
    texto = _normalizar_unicode(re.sub(r"\n{3,}", "\n\n", "".join(s if s.endswith("\n") else s + "\n" for s in saida)))
    if len(re.sub(r"<!--.*?-->|\s+", "", texto)) < 300:
        raise ErroLeitura("o PDF não tem texto extraível suficiente (escaneado sem OCR?).")
    figuras = _extrair_figuras(doc, pdf, pasta_figuras, legendas, max_figuras, dpi)
    return Leitura(texto, figuras, tabelas)

def _texto_celula(caixa, palavras) -> str:
    """Texto da célula a partir das palavras cujo centro cai dentro dela (evita quebras como '421 .')."""
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
    """Recorta as figuras da página (imagens e gráficos vetoriais) em JPEG compacto."""
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
            if uso_xref[info[0]] > 1:  # logotipos e marcas repetidas
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


# MD
def ler_md(md: Path) -> Leitura:
    """Lê um .md existente (sem conversão). Imagens referenciadas entram nas fichas."""
    texto = _normalizar_unicode(ler_texto(md, errors="replace"))
    if "<!-- p. " not in texto:
        texto = "<!-- p. 1 -->\n" + texto
    figuras = []
    for alt, alvo in re.findall(r"!\[([^\]]*)\]\(([^)\s]+)", texto):
        arq = (md.parent / alvo)
        if existe(arq) and arq.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".bmp"):
            figuras.append(Figura(arq, 0, alt.strip()))
    return Leitura(texto, figuras[:8])

def _normalizar_unicode(texto: str) -> str:
    for lig, sub in _LIGADURAS_UNICODE.items():
        texto = texto.replace(lig, sub)
    texto = texto.replace("­", "").replace("​", "")
    return unicodedata.normalize("NFC", texto)


_RE_PALAVRA = re.compile(r"[A-Za-z]{2,}")
_PUA = "-"  # área de uso privado: algumas fontes põem ali os glifos de ligadura
_RE_PALAVRA_PUA = re.compile(rf"[A-Za-z{_PUA}]*[{_PUA}][A-Za-z{_PUA}]*")


def frequencia_documental(textos: Iterable[str]) -> Counter:
    df: Counter = Counter()
    for texto in textos:
        df.update({p.lower() for p in _RE_PALAVRA.findall(re.sub(rf"[A-Za-z]*[{_PUA}][A-Za-z{_PUA}]*", " ", texto))})
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
    melhor = max(candidatos, key=lambda c: (df.get(c.lower(), 0), -len(c)))
    return melhor if df.get(melhor.lower(), 0) > 0 else re.sub(f"[{_PUA}]", "", palavra)


_CURTAS_QUEBRADAS = {"rst", "nal", "eld", "uid", "ber", "lms", "ows", "lm"}
_PROTEGIDAS = {"oral", "orally", "ash", "ashes", "ashy", "ask", "asks", "asked", "lies", "lame", "owing", "ever", "ore", "ores"}


def _melhor_reparo(palavra: str, df: Counter, limite_raro: int) -> str | None:
    if (len(palavra) < 4 and palavra not in _CURTAS_QUEBRADAS) or palavra in _PROTEGIDAS:
        return None
    melhor, melhor_df = None, 0
    for i in range(len(palavra) + 1):
        for ins in _INSERCOES:
            candidata = palavra[:i] + ins + palavra[i:]
            n = df.get(candidata, 0)
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

def eh_sumario(texto: str) -> bool:
    """Documento que só contém capa e sumário (ex.: anais de congresso)."""
    linhas = [l for l in texto.splitlines() if l.strip() and not l.startswith("<!--")]
    if not linhas:
        return True
    pontilhadas = sum(1 for l in linhas if re.search(r"(?:\.\s?){5,}\s*\d+\s*$", l) or re.search(r"\.{5,}", l))
    return pontilhadas / len(linhas) > 0.2

def duracao(segundos: float) -> str:
    m, s = divmod(int(math.ceil(segundos)), 60)
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}min" if h else f"{m}min{s:02d}s"
