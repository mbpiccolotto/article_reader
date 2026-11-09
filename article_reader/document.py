"""Geração da síntese e ficha."""

from __future__ import annotations

import io
import re
import sys
import os
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from typing import Any
from .citations import ordenar_referencias, referencia_abnt
from .files import ler_bytes
from .grammar import pl
from .models import Artigo
from .writing import IT_FIM, IT_INI, Documento


FONTE = "Times New Roman"


def _configurar_estilos(doc: Any) -> None:
    for secao in doc.sections:
        secao.top_margin = secao.left_margin = Cm(3)
        secao.bottom_margin = secao.right_margin = Cm(2)
    normal = doc.styles["Normal"]
    normal.font.name = FONTE
    normal.font.size = Pt(12)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), FONTE)
    normal.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(0)
    for nome in ("Heading 1", "Heading 2"):
        estilo = doc.styles[nome]
        estilo.font.name = FONTE
        estilo.font.size = Pt(12)
        estilo.font.bold = nome == "Heading 1"
        estilo.font.italic = False
        estilo.font.color.rgb = RGBColor(0, 0, 0)
        fontes = estilo.element.get_or_add_rPr().get_or_add_rFonts()
        for atributo in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
            fontes.attrib.pop(qn(atributo), None)
        for atributo in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
            fontes.set(qn(atributo), FONTE)
        estilo.paragraph_format.space_before = Pt(18 if nome == "Heading 1" else 12)
        estilo.paragraph_format.space_after = Pt(12 if nome == "Heading 1" else 6)
        estilo.paragraph_format.keep_with_next = True
        estilo.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE

def _escrever_trechos(paragrafo, texto: str, tamanho: Pt | None = None) -> None:
    """Escreve o texto respeitando os marcadores de itálico."""
    partes = re.split(f"({IT_INI}.*?{IT_FIM})", texto)
    for parte in partes:
        if not parte:
            continue
        italico = parte.startswith(IT_INI)
        run = paragrafo.add_run(parte.strip(IT_INI + IT_FIM))
        run.italic = italico
        if tamanho:
            run.font.size = tamanho


NOTAS = {
    "pdf": "a partir da leitura integral de {n} em PDF, {lidos} diretamente (sem conversão intermediária)",
    "md": "a partir da leitura integral de {n} em Markdown",
    "ris": "a partir dos resumos de {n} (RIS); como não há texto integral, as citações "
           "diretas vêm dos resumos e não indicam página",
}


def gerar_docx(documento: Documento, artigos: list[Artigo], destino: Path, titulo: str, tipo: str = "pdf") -> None:
    por_chave = {a.chave: a for a in artigos}
    doc = Document()
    _configurar_estilos(doc)

    cabecalho = doc.add_paragraph()
    cabecalho.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cabecalho.add_run(titulo.upper()).bold = True
    cabecalho.paragraph_format.space_after = Pt(18)

    nota = doc.add_paragraph()
    nota.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    nota.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    nota.paragraph_format.space_after = Pt(18)
    r = nota.add_run(
        f"Nota: texto-base gerado automaticamente, por regras em Python, {NOTAS[tipo].format(n=pl(len(artigos), 'registro bibliográfico', 'registros bibliográficos') if tipo == 'ris' else pl(len(artigos), 'artigo'), lidos='lido' if len(artigos) == 1 else 'lidos')}. "
        "Os achados são citações diretas extraídas dos textos originais; "
        "a organização em eixos e temas resulta de agrupamento estatístico. Revise o texto e confira os trechos "
        "assinalados no documento de fichas e relatório de leitura antes de incorporá-lo ao trabalho."
    )
    r.italic = True
    r.font.size = Pt(10)

    for bloco in documento.blocos:
        if bloco.tipo == "titulo1":
            doc.add_heading(bloco.texto.upper(), level=1)
        elif bloco.tipo == "titulo2":
            doc.add_heading(bloco.texto, level=2)
        elif bloco.tipo == "citacao_longa":
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            fmt = p.paragraph_format
            fmt.left_indent = Cm(4)
            fmt.line_spacing_rule = WD_LINE_SPACING.SINGLE
            fmt.space_before = Pt(12)
            fmt.space_after = Pt(12)
            _escrever_trechos(p, bloco.texto, Pt(10))
        else:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.first_line_indent = Cm(1.25)
            _escrever_trechos(p, bloco.texto)

    doc.add_page_break()
    titulo_ref = doc.add_heading("REFERÊNCIAS", level=1)
    titulo_ref.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for artigo in ordenar_referencias([por_chave[c] for c in documento.citados if c in por_chave]):
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
        p.paragraph_format.space_after = Pt(12)
        for trecho, negrito in referencia_abnt(artigo):
            p.add_run(trecho).bold = negrito

    destino.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(destino))

def _tabela(doc: Any, cabecalho: list[str], linhas: list[list[str]], tamanho: float = 9, larguras=None):
    tab = doc.add_table(rows=1, cols=len(cabecalho))
    tab.style = "Table Grid"
    for i, texto in enumerate(cabecalho):
        cel = tab.rows[0].cells[i]
        cel.text = ""
        run = cel.paragraphs[0].add_run(str(texto))
        run.bold = True
        run.font.size = Pt(tamanho)
    for linha in linhas:
        celulas = tab.add_row().cells
        for i, texto in enumerate(linha[: len(cabecalho)]):
            celulas[i].text = ""
            run = celulas[i].paragraphs[0].add_run(str(texto))
            run.font.size = Pt(tamanho)
    for linha in tab.rows:
        for cel in linha.cells:
            for p in cel.paragraphs:
                p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    if larguras:
        for linha in tab.rows:
            for cel, larg in zip(linha.cells, larguras):
                cel.width = Cm(larg)
    doc.add_paragraph()
    return tab

def _campo(doc: Any, rotulo: str, valor: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    p.paragraph_format.space_after = Pt(3)
    p.add_run(f"{rotulo}: ").bold = True
    p.add_run(valor or "—")

def gerar_ficha_relatorio(artigos: list[Artigo], eixos, documento: Documento, falhas: list[str], info: dict,
                          leituras: dict, destino: Path, titulo: str, avancar=None, situacao: dict | None = None) -> None:
    from .citations import citacao, pagina_citada

    doc = Document()
    _configurar_estilos(doc)
    cab = doc.add_paragraph()
    cab.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cab.add_run("FICHAS E RELATÓRIO DE LEITURA").bold = True
    sub = doc.add_paragraph()
    sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sub.add_run(titulo).italic = True
    sub.paragraph_format.space_after = Pt(18)

    # Relatório
    doc.add_heading("1 RELATÓRIO DE PROCESSAMENTO", level=1)
    for rotulo, valor in info.items():
        _campo(doc, rotulo, str(valor))
    doc.add_heading("1.1 Eixos temáticos", level=2)
    _tabela(doc, ["Eixo", "Estudos", "Termos característicos", "Temas (nº de trechos)"],
            [[e.titulo, str(len(e.artigos)), ", ".join(e.termos) or "—",
              ", ".join(f"{t.rotulo} ({len(t.trechos)})" for t in e.temas) or "—"] for e in eixos],
            larguras=[4.5, 1.6, 4.5, 5.4])
    doc.add_heading("1.2 Artigos analisados", level=2)
    _tabela(doc, ["Arquivo", "Citação", "R", "D", "C", "L", "Metadados", "Alertas"],
            [[a.arquivo + ("" if a.chave in documento.citados else " (não citado)"), citacao(a),
              str(len(a.resultados)), str(len(a.discussoes)), str(len(a.conclusoes)),
              a.metadados.fonte, " / ".join(a.alertas) or "—"] for a in sorted(artigos, key=lambda x: x.arquivo)],
            tamanho=8, larguras=[3.4, 2.6, 0.7, 0.7, 0.7, 0.7, 1.6, 5.6])
    nota = doc.add_paragraph("R/D/C/L = trechos de resultados, discussão e conclusões.")
    nota.runs[0].font.size = Pt(9)
    if situacao:
        doc.add_heading("1.3 Situação de cada arquivo", level=2)
        ordem = {"f": 0, "n": 1, "d": 2, "a": 3}  # falhas e não analisados primeiro
        _tabela(doc, ["Arquivo", "Situação"],
                [[n, s] for n, s in sorted(situacao.items(), key=lambda kv: (ordem.get(kv[1][:1], 4), kv[0].lower()))],
                tamanho=8, larguras=[8.0, 8.0])
    elif falhas:
        doc.add_heading("1.3 Itens não analisados", level=2)
        for f in falhas:
            p = doc.add_paragraph(f.replace("`", ""), style="List Bullet")
            p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE

    # Fichas
    doc.add_page_break()
    doc.add_heading("2 FICHAS DE LEITURA", level=1)
    intro = doc.add_paragraph(
        "Trechos selecionados automaticamente de cada artigo, com página (do periódico quando a paginação é "
        "conhecida; senão, do PDF) e pontuação de relevância, seguidos das figuras e tabelas extraídas. Use as "
        "fichas para conferir e, se necessário, substituir trechos da síntese.")
    intro.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    for n, a in enumerate(sorted(artigos, key=lambda x: (x.metadados.ano, x.chave)), 1):
        if avancar:
            avancar(a.arquivo)
        m = a.metadados
        doc.add_heading(f"2.{n} {citacao(a)} — {m.titulo or a.arquivo}", level=2)
        p = doc.add_paragraph()
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
        p.paragraph_format.space_after = Pt(3)
        p.add_run("Referência: ").bold = True
        for trecho, negrito in referencia_abnt(a):
            p.add_run(trecho).bold = negrito
        _campo(doc, "Arquivo", a.arquivo)
        _campo(doc, "Metadados obtidos de", {"ris": "RIS", "crossref": "Crossref", "pdf": "texto do PDF"}.get(m.fonte, m.fonte))
        if m.palavras_chave:
            _campo(doc, "Palavras-chave", "; ".join(m.palavras_chave[:12]))
        _campo(doc, "Seções reconhecidas", ", ".join(a.categorias_encontradas))
        _campo(doc, "Técnicas detectadas", ", ".join(a.tecnicas))
        if a.alertas:
            _campo(doc, "Alertas", " / ".join(a.alertas))
        for nome, frases in (("Resultados", a.resultados), ("Discussão", a.discussoes),
                             ("Conclusões", a.conclusoes)):
            t = doc.add_paragraph()
            t.paragraph_format.space_before = Pt(6)
            t.add_run(nome).bold = True
            if not frases:
                doc.add_paragraph("—", style="List Bullet")
            for f in frases:
                pag = f"p. {pagina_citada(a, f.pagina)}" if f.pagina else "resumo"
                item = doc.add_paragraph(style="List Bullet")
                item.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                item.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
                r = item.add_run(f"({pag}; {f.pontuacao:.1f}) ")
                r.font.size = Pt(10)
                r.font.color.rgb = RGBColor(0x59, 0x59, 0x59)
                item.add_run(f.texto)
        leitura = leituras.get(a.arquivo)
        if leitura and leitura.figuras:
            t = doc.add_paragraph()
            t.paragraph_format.space_before = Pt(6)
            t.add_run(f"Figuras ({len(leitura.figuras)})").bold = True
            for k, fig in enumerate(leitura.figuras, 1):
                try:
                    doc.add_picture(io.BytesIO(ler_bytes(fig.arquivo)), width=Cm(12))
                    doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
                except Exception:  # noqa: BLE001 — formato de imagem não suportado
                    continue
                leg = doc.add_paragraph()
                leg.alignment = WD_ALIGN_PARAGRAPH.CENTER
                leg.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
                leg.paragraph_format.space_after = Pt(10)
                rl = leg.add_run((fig.legenda or f"Figura {k} (legenda não identificada)")
                                 + (f" — p. {pagina_citada(a, fig.pagina)}" if fig.pagina else ""))
                rl.font.size = Pt(9)
        if leitura and leitura.tabelas:
            t = doc.add_paragraph()
            t.paragraph_format.space_before = Pt(6)
            t.add_run(f"Tabelas ({len(leitura.tabelas)})").bold = True
            for tab in leitura.tabelas[:5]:
                leg = doc.add_paragraph()
                leg.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
                rl = leg.add_run((tab.legenda or "Tabela (legenda não identificada)") + f" — p. {pagina_citada(a, tab.pagina)}")
                rl.font.size = Pt(9)
                rl.italic = True
                colunas = min(len(tab.linhas[0]), 8)
                _tabela(doc, tab.linhas[0][:colunas], [l[:colunas] for l in tab.linhas[1:26]], tamanho=7)
    destino.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(destino))
