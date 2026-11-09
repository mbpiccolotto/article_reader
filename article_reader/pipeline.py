"""Pipeline de leitura."""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
import time
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path

from . import glossary as glossario_mod
from .passage_selection import detectar_tecnicas, selecionar_trechos
from .file_io import ler_bytes, ler_texto, listar_recursivo
from .citations import atribuir_chaves
from .config import TIPOS, VERSAO, Config
from .docx_builder import gerar_docx, gerar_ficha_relatorio
from .document_reader import ErroLeitura, Leitura, duracao, eh_sumario, frequencia_documental, ler_md, ler_pdf, reparar_corpus
from .metadata import (associar_ris, dois_no_texto, ler_ris, metadados_do_texto, normalizar, textos_parecidos,
                       titulo_do_arquivo, titulos_de_cabecalho)
from .models import Artigo, Metadados
from .pluralization import pl, vb
from .progress_bar import BarraProgresso, Carregando
from .summary_writer import redigir
from .section_parser import FraseBruta, dividir_frases, ler_markdown
from .thematic_axes import construir_eixos


# Reconhecimento
"""Encontra os arquivos de entrada e cria nomes e caminhos de saída."""

EXTENSOES = {"pdf": (".pdf",), "ris": (".ris", ".txt"), "md": (".md", ".markdown")}

def log(msg: str) -> None:
    print(msg, flush=True)

INACESSIVEIS: list[str] = []

def listar_arquivos(pasta: Path, tipo: str) -> list[Path]:
    arquivos, inacessiveis = listar_recursivo(pasta, EXTENSOES[tipo])
    INACESSIVEIS.extend(p for p in inacessiveis if p not in INACESSIVEIS)
    if tipo == "ris":
        arquivos = [p for p in arquivos if p.suffix.lower() == ".ris" or _parece_ris(p)]
    return arquivos

def rotulo(arq: Path, pasta: Path) -> str:
    try:
        return arq.relative_to(pasta).as_posix()
    except ValueError:
        return arq.name

def _parece_ris(p: Path) -> bool:
    try:
        return bool(re.search(r"^TY  - ", ler_texto(p, errors="replace")[:5000], re.MULTILINE))
    except OSError:
        return False

def pasta_downloads() -> Path:
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                            ("Data4", ctypes.c_ubyte * 8)]

            guid = GUID(0x374DE290, 0x123F, 0x4565, (ctypes.c_ubyte * 8)(0x91, 0x64, 0x39, 0xC4, 0x92, 0x5E, 0x46, 0x7B))
            caminho = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(caminho)) == 0:
                valor = caminho.value
                ctypes.windll.ole32.CoTaskMemFree(caminho)
                if valor:
                    return Path(valor)
        except Exception:
            pass
    return Path.home() / "Downloads"

def nome_seguro(nome: str) -> str:
    nome = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", nome).strip(" .")
    return nome[:100] or "resultados_leitura"

def caminho_livre(destino: Path) -> Path:
    if not destino.exists():
        return destino
    for i in range(2, 1000):
        candidato = destino.with_name(f"{destino.stem} ({i}){destino.suffix}")
        if not candidato.exists():
            return candidato
    return destino


# Caminho Principal
"""Executa as cinco etapas: leitura, seleção, eixos, redação do resumo e documentos."""

def executar(cfg: Config) -> Path:
    inicio = time.time()
    tipo = cfg.tipo
    INACESSIVEIS.clear()
    arquivos = listar_arquivos(cfg.pasta_entrada, tipo)
    if not arquivos:
        raise RuntimeError(f"Nenhum arquivo {TIPOS[tipo]} encontrado em {cfg.pasta_entrada}.")
    trabalho = Path(tempfile.mkdtemp(prefix="article_reader_"))
    try:
        log(f"ETAPA 1/5 — Leitura: {pl(len(arquivos), f'arquivo {TIPOS[tipo]}', f'arquivos {TIPOS[tipo]}')}")
        if INACESSIVEIS:
            log(f"  Atenção: {pl(len(INACESSIVEIS), 'pasta', 'pastas')} sem permissão de leitura: {', '.join(INACESSIVEIS[:3])}")
        if tipo == "ris":
            artigos, falhas, leituras, situacao = _artigos_de_ris(arquivos, cfg)
        else:
            artigos, falhas, leituras, situacao = _artigos_de_textos(arquivos, cfg, trabalho)
        if not artigos:
            raise RuntimeError("Nenhum artigo pôde ser lido. " + " ".join(falhas[:5]))
        atribuir_chaves(artigos)

        log("\nETAPA 3/5 — Organização em eixos temáticos")
        with Carregando("Agrupando em eixos"):
            glossario = glossario_mod.carregar(cfg.glossario)
            eixos = construir_eixos(artigos, cfg, glossario, lambda *_: None)
        for e in eixos:
            log(f"  • {e.titulo} — {pl(len(e.artigos), 'estudo')}; temas: {', '.join(t.rotulo for t in e.temas) or '—'}")

        log("\nETAPA 4/5 — Redação do resumo integralizado")
        with Carregando("Redigindo"):
            documento = redigir(artigos, eixos, cfg)

        log("\nETAPA 5/5 — Documentos e pacote .zip")
        nome = nome_seguro(cfg.nome_output)
        doc_resumo = trabalho / f"{nome} - resumo integralizado.docx"
        doc_fichas = trabalho / f"{nome} - ficha e relatorio de leitura.docx"
        with Carregando("Resumo integralizado (.docx)"):
            gerar_docx(documento, artigos, doc_resumo, cfg.titulo, tipo)
        fontes = Counter(a.metadados.fonte for a in artigos)
        contagem = contar_situacoes(situacao)
        info = {
            "Versão do programa": VERSAO,
            "Data": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "Tipo de entrada": TIPOS[tipo],
            "Pasta de entrada": str(Path(cfg.pasta_entrada).resolve()),
            "Arquivos encontrados": len(arquivos),
            **({"Registros nos arquivos RIS": len(situacao)} if tipo == "ris" else {}),
            "Artigos analisados": len(artigos),
            "Duplicatas descartadas (mesmo artigo em outro arquivo)": contagem["duplicatas"],
            "Falhas de leitura": contagem["falhas"],
            "Não analisados por outro motivo": contagem["outros"],
            **({"Pastas sem permissão de leitura": "; ".join(INACESSIVEIS)} if INACESSIVEIS else {}),
            "Metadados": ", ".join(f"{k}: {v}" for k, v in fontes.items()),
            "Citações diretas no resumo": documento.trechos_usados,
            "Artigos citados no resumo": f"{len(documento.citados)} de {len(artigos)}",
            "Eixos temáticos": len(eixos),
            "Figuras extraídas": sum(len(l.figuras) for l in leituras.values()),
            "Tabelas extraídas": sum(len(l.tabelas) for l in leituras.values()),
            "Tempo total": duracao(time.time() - inicio),
        }
        barra = BarraProgresso(len(artigos), "Fichas de leitura (.docx)")
        gerar_ficha_relatorio(artigos, eixos, documento, falhas, info, leituras, doc_fichas, cfg.titulo, barra.avancar,
                              situacao=situacao)
        barra.fim()

        destino_dir = Path(cfg.pasta_output) if cfg.pasta_output else pasta_downloads()
        destino_dir.mkdir(parents=True, exist_ok=True)
        zip_final = caminho_livre(destino_dir / f"{nome}.zip")
        with Carregando("Compactando em .zip"):
            with zipfile.ZipFile(zip_final, "w", zipfile.ZIP_DEFLATED) as z:
                z.write(doc_resumo, doc_resumo.name)
                z.write(doc_fichas, doc_fichas.name)
    finally:
        shutil.rmtree(trabalho, ignore_errors=True)

    nao_citados = [a for a in artigos if a.chave not in documento.citados]
    log("\n" + "=" * 64)
    log(" CONCLUÍDO")
    log("=" * 64)
    log(f"  {'Registros encontrados' if tipo == 'ris' else 'Arquivos encontrados'}:{' ' * (6 if tipo == 'ris' else 7)}"
        f"{len(situacao) if tipo == 'ris' else len(arquivos)}")
    log(f"  Artigos analisados:         {len(artigos)}")
    if contagem["duplicatas"]:
        log(f"  Duplicatas descartadas:     {contagem['duplicatas']} (o mesmo artigo em outro arquivo; lista no relatório)")
        for nome, s in [(n, s) for n, s in situacao.items() if s.startswith("duplicata")][:5]:
            log(f"    - {nome}: {s}")
    if contagem["falhas"] or contagem["outros"]:
        log(f"  Não analisados:             {contagem['falhas'] + contagem['outros']} (motivos no relatório)")
    log(f"  Eixos temáticos:            {len(eixos)}")
    log(f"  Citações diretas no resumo: {documento.trechos_usados}")
    log(f"  Artigos citados:            {len(artigos) - len(nao_citados)} de {len(artigos)}")
    log(f"  Artigos com alertas:        {sum(1 for a in artigos if a.alertas)} (ver ficha e relatório)")
    for f in falhas[:10]:
        log(f"    - não analisado: {f.replace('`', '')}")
    if len(falhas) > 10:
        log(f"    ... e mais {len(falhas) - 10} (lista completa no relatório)")
    log(f"  Tempo total:                {duracao(time.time() - inicio)}")
    log(f"\n  Resultados: {zip_final}")
    return zip_final

def contar_situacoes(situacao: dict[str, str]) -> Counter:
    c = Counter({"analisados": 0, "duplicatas": 0, "falhas": 0, "outros": 0})
    for s in situacao.values():
        c["analisados" if s.startswith("analisado") else "duplicatas" if s.startswith("duplicata")
          else "falhas" if s.startswith("falha") else "outros"] += 1
    return c


# Output
"""Transforma os textos lidos em objetos Artigo."""

def _artigos_de_textos(arquivos: list[Path], cfg: Config, trabalho: Path):
    falhas: list[str] = []
    situacao: dict[str, str] = {}
    leituras: dict[str, Leitura] = {}
    ocr: dict[str, bool] = {}
    arquivos_ris = listar_arquivos(cfg.pasta_entrada, "ris")
    registros = _ler_registros(arquivos_ris)
    if registros:
        log(f"  RIS na pasta: {pl(len(registros), 'registro', 'registros')} (usados como metadados das referências).")

    por_hash: dict[str, str] = {}
    barra = BarraProgresso(len(arquivos), "Lendo")
    for i, arq in enumerate(arquivos):
        nome = rotulo(arq, cfg.pasta_entrada)
        try:
            dados = ler_bytes(arq)
            impressao = hashlib.sha1(dados).hexdigest()
            if impressao in por_hash:
                situacao[nome] = f"duplicata exata de {por_hash[impressao]} (mesmo conteúdo)"
                barra.avancar(nome)
                continue
            por_hash[impressao] = nome
            if cfg.tipo == "pdf":
                leitura = ler_pdf(arq, trabalho / "figuras" / f"{i:04d}", extrair_tabelas=cfg.tabelas,
                                  max_figuras=cfg.figuras, dpi_figuras=cfg.dpi_figuras)
            else:
                leitura = ler_md(arq)
            leituras[nome] = leitura
            ocr[nome] = leitura.ocr
        except (ErroLeitura, OSError) as erro:
            causa = getattr(erro, "strerror", None) or str(erro)
            falhas.append(f"`{nome}`: {causa}")
            situacao[nome] = f"falha na leitura: {causa}"
            barra.mensagem(f"  FALHA em {nome}: {causa}")
        barra.avancar(nome)
    figs = sum(len(l.figuras) for l in leituras.values())
    tabs = sum(len(l.tabelas) for l in leituras.values())
    barra.fim(f"{pl(len(leituras), 'arquivo lido', 'arquivos lidos')}; {pl(figs, 'figura extraída', 'figuras extraídas')} e "
              f"{pl(tabs, 'tabela extraída', 'tabelas extraídas')}.")

    textos = reparar_corpus({n: l.texto for n, l in leituras.items()},
                            [r.titulo + " " + r.resumo for r in registros], log)
    for n, txt in textos.items():
        leituras[n].texto = txt

    log("\nETAPA 2/5 — Seções, trechos e identificação bibliográfica")
    vocabulario = frequencia_documental(list(textos.values()) + [r.titulo + " " + r.resumo for r in registros])
    inicios = {n: "\n".join(txt.splitlines()[:250]) for n, txt in textos.items()}
    associacoes = associar_ris(inicios, registros) if registros else {}
    cabecalhos = titulos_de_cabecalho({n: t for n, t in inicios.items() if n not in associacoes})

    candidatos: list[tuple[str, Metadados, list[str]]] = []
    for nome, texto in sorted(textos.items()):
        if eh_sumario(texto):
            falhas.append(f"`{nome}`: contém apenas capa/sumário (não há texto do artigo).")
            situacao[nome] = "não analisado: contém apenas capa/sumário"
            continue
        alertas: list[str] = []
        if nome in associacoes:
            meta, confianca = associacoes[nome]
            if confianca < 0.95:
                alertas.append(f"Registro RIS associado pelo título (similaridade {confianca:.0%}); confira.")
        else:
            meta = metadados_do_texto(inicios[nome], nome, cabecalhos)
            alertas.append("Sem registro RIS correspondente: título obtido do texto/nome do arquivo; "
                           "autores, ano e periódico ausentes (a citação ficará incompleta).")
        candidatos.append((nome, meta, alertas))

    grupos: dict[str, list[int]] = {}
    motivo: dict[int, str] = {}
    sem_doi: list[int] = []
    for i, (nome, meta, _) in enumerate(candidatos):
        if meta.doi:
            grupos.setdefault(meta.doi.lower(), []).append(i)
            motivo[i] = "mesmo DOI"
        else:
            sem_doi.append(i)
    por_titulo: dict[str, set[str]] = {}
    for chave, indices in grupos.items():
        titulo = normalizar(candidatos[indices[0]][1].titulo)
        if len(titulo) >= 25:
            por_titulo.setdefault(titulo, set()).add(chave)
    for i in sem_doi:
        nome, meta, _ = candidatos[i]
        cabecalho = "\n".join(inicios[nome].splitlines()[:60])
        dois_cabecalho = dois_no_texto(cabecalho)
        destino = next((d for d in dois_cabecalho[:6] if d in grupos), None)
        motivo[i] = "mesmo DOI no texto"
        if destino is None:
            titulo = normalizar(meta.titulo)
            if titulo == normalizar(titulo_do_arquivo(nome)) or titulo in cabecalhos:
                titulo = ""
            alvos = por_titulo.get(titulo, set()) if len(titulo) >= 25 else set()
            if len(alvos) == 1:
                destino = next(iter(alvos))
                motivo[i] = "mesmo título"
            elif dois_cabecalho:
                # O primeiro DOI do cabeçalho é o do próprio artigo: arquivos com DOIs diferentes nunca são duplicatas,
                # mesmo que o título extraído do texto coincida (cabeçalho de periódico, título dividido em linhas).
                destino = f"doi:{dois_cabecalho[0]}"
            elif len(titulo) >= 25 and not alvos:
                destino = f"titulo:{titulo}"
                if not all(textos_parecidos(textos[nome], textos[candidatos[j][0]]) for j in grupos.get(destino, [])):
                    destino = f"arquivo:{nome}"
                motivo[i] = "mesmo título"
            else:
                destino = f"arquivo:{nome}"
        grupos.setdefault(destino, []).append(i)
    manter: set[int] = set()
    for indices in grupos.values():
        melhor = max(indices, key=lambda i: (bool(candidatos[i][1].doi), not ocr[candidatos[i][0]], len(textos[candidatos[i][0]])))
        manter.add(melhor)
        for i in indices:
            if i != melhor:
                situacao[candidatos[i][0]] = (f"duplicata de {candidatos[melhor][0]} "
                                              f"({motivo.get(i, 'mesmo artigo')}; mantida a melhor cópia)")

    artigos: list[Artigo] = []
    barra = BarraProgresso(len(manter), "Analisando")
    for i in sorted(manter):
        nome, meta, alertas = candidatos[i]
        barra.avancar(nome)
        texto = textos[nome]
        frases, categorias = ler_markdown(texto)
        artigo = Artigo(arquivo=nome, metadados=meta, categorias_encontradas=categorias, alertas=alertas)
        artigo.deslocamento_pagina = _deslocamento(meta, texto)
        if ocr[nome]:
            artigo.alertas.append("Texto obtido por OCR: confira a grafia das citações no PDF.")
        selecionar_trechos(artigo, frases, cfg, vocabulario)
        metodos = " ".join(f.texto for f in frases if f.categoria in ("metodos", "resumo", "pre"))
        artigo.tecnicas = detectar_tecnicas(" ".join([meta.titulo, meta.resumo, " ".join(meta.palavras_chave), metodos]))
        artigos.append(artigo)
        situacao[nome] = "analisado" + (f" ({len(artigo.alertas)} {vb(len(artigo.alertas), 'alerta', 'alertas')})" if artigo.alertas else "")
    trechos = sum(len(a.resultados) + len(a.discussoes) + len(a.conclusoes) for a in artigos)
    com_alerta = sum(1 for a in artigos if a.alertas)
    barra.fim(f"{pl(len(artigos), 'artigo analisado', 'artigos analisados')}; {pl(trechos, 'trecho selecionado', 'trechos selecionados')}; "
              f"{com_alerta} com {vb(com_alerta, 'alerta', 'alertas')}.")
    return artigos, falhas, leituras, situacao


# Registro RIS
"""Monta artigos a partir de registros RIS."""

def _deslocamento(meta: Metadados, texto: str) -> int:
    try:
        inicial, final = int(meta.pagina_inicial), int(meta.pagina_final)
    except ValueError:
        return 0
    paginas_pdf = len(re.findall(r"<!-- p\. \d+ -->", texto))
    if final >= inicial and abs((final - inicial + 1) - paginas_pdf) <= 1:
        return inicial - 1
    return 0

def _ler_registros(arquivos_ris: list[Path], duplicados: list | None = None) -> list[Metadados]:
    registros, vistos = [], set()
    for arq in arquivos_ris:
        try:
            lidos = ler_ris(arq)
        except (OSError, RuntimeError) as erro:
            log(f"  Não foi possível ler {arq.name}: {erro}")
            continue
        for r in lidos:
            chave = r.doi or normalizar(r.titulo)
            if chave and chave not in vistos:
                vistos.add(chave)
                registros.append(r)
            elif duplicados is not None:
                duplicados.append(r)
    return registros

def _artigos_de_ris(arquivos: list[Path], cfg: Config):
    repetidos: list[Metadados] = []
    registros = _ler_registros(arquivos, repetidos)
    situacao: dict[str, str] = {}
    def chave_unica(texto: str) -> str:
        chave, n = texto, 2
        while chave in situacao:
            chave, n = f"{texto} ({n})", n + 1
        return chave

    for r in repetidos:
        situacao[chave_unica(f"{(r.titulo or 'sem título')[:80]} [repetido]")] = \
            "duplicata: registro repetido (mesmo DOI ou título) em outro arquivo RIS"
    log(f"  {pl(len(registros), 'registro único', 'registros únicos')} em {pl(len(arquivos), 'arquivo RIS', 'arquivos RIS')}"
        + (f" ({pl(len(repetidos), 'repetido descartado', 'repetidos descartados')})" if repetidos else "") + ".")
    log("\nETAPA 2/5 — Trechos dos resumos")
    vocabulario = frequencia_documental([r.titulo + " " + r.resumo for r in registros])
    artigos, falhas = [], []
    barra = BarraProgresso(len(registros), "Analisando")
    for i, meta in enumerate(registros, 1):
        nome_reg = chave_unica((meta.titulo or f"registro {i}")[:80])
        barra.avancar(nome_reg)
        if len(meta.resumo.split()) < 40:
            falhas.append(f"`{nome_reg}`: registro sem resumo suficiente (campo AB vazio ou curto).")
            situacao[nome_reg] = "não analisado: registro sem resumo suficiente"
            continue
        sentencas = dividir_frases(re.sub(r"\s+", " ", meta.resumo))
        frases = []
        for k, s in enumerate(sentencas):
            categoria = "conclusao" if k >= len(sentencas) - 2 else "resultados_discussao"
            frases.append(FraseBruta(s, 0, categoria, "Resumo", k, False))
        artigo = Artigo(arquivo=nome_reg, metadados=meta,
                        categorias_encontradas=["resultados_discussao", "conclusao"],
                        alertas=["Leitura baseada apenas no resumo (registro RIS, sem texto integral)."])
        selecionar_trechos(artigo, frases, cfg, vocabulario)
        artigo.tecnicas = detectar_tecnicas(" ".join([meta.titulo, meta.resumo, " ".join(meta.palavras_chave)]))
        artigos.append(artigo)
        situacao[nome_reg] = "analisado (somente o resumo)"
    barra.fim(f"{pl(len(artigos), 'registro analisado', 'registros analisados')}; "
              f"{len(falhas)} sem resumo suficiente.")
    return artigos, falhas, {}, situacao
