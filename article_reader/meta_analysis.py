"""Análises reprodutíveis da revisão sistemática"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import logging
import platform
import re
import shutil
import sys
import unicodedata
import zipfile
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import font_manager
from PIL import Image, ImageDraw, ImageFont
from scipy import stats
import matplotlib.ticker
import matplotlib.colors


# Constantes
LOGGER = logging.getLogger("revisao")
SEMENTE = 20261030
Image.MAX_IMAGE_PIXELS = None


# Estrutura da Análise
ESQUEMA_PADRAO: dict = {
    "versao_esquema": "1.0",
    "campos_estudo": {
        "autores": "Autores como aparecem no artigo",
        "ano": "Ano de publicação",
        "titulo": "Título do artigo",
        "periodico": "Periódico",
        "doi": "DOI, se presente",
        "pais": "País onde o estudo foi conduzido",
        "desenho_estudo": "Desenho do estudo, como descrito pelos autores",
        "matriz": "Matriz, material, população ou sistema estudado",
        "tecnica": "Técnica/método analítico principal",
        "n_amostral": "Tamanho amostral total (número de amostras/participantes)",
    },

    "variaveis_fisicoquimicas": {
        "ph": {"rotulo": "pH", "dimensao": "adimensional"},
        "temperatura": {"rotulo": "Temperatura", "dimensao": "temperatura"},
        "tempo": {"rotulo": "Tempo de exposição/ensaio", "dimensao": "tempo"},
        "concentracao": {"rotulo": "Concentração", "dimensao": "concentracao_massa"},
        "condutividade": {"rotulo": "Condutividade elétrica", "dimensao": "condutividade"},
        "umidade": {"rotulo": "Umidade", "dimensao": "fracao"},
    },

    "variaveis_ensaio_criticas": ["valor", "unidade", "dp", "ep", "ic_inferior", "ic_superior", "n"],
    "variaveis_estudo_criticas": ["ano", "pais", "desenho_estudo", "matriz", "tecnica", "n_amostral"],

    "agrupamentos_desfecho": {
        "eficiencia_remocao": ["remocao", "removal", "eficiencia", "efficiency", "degradacao", "degradation"],
        "toxicidade": ["toxic", "ec50", "lc50", "ic50", "mortalidade", "mortality", "viabilidade", "viability"],
        "atividade_antioxidante": ["antioxid", "dpph", "abts", "frap", "orac"],
        "atividade_antimicrobiana": ["antimicrob", "antibacter", "mic", "cim", "halo", "inibicao", "inhibition"],
        "composicao": ["teor", "content", "composicao", "composition", "concentracao", "concentration"],
        "propriedade_fisica": ["viscosidade", "viscosity", "densidade", "density", "tamanho de particula", "particle size"],
    },
    "mapeamento_categorias": {
        "desenho_estudo": {
            "experimental_laboratorial": ["laborat", "in vitro", "bancada", "bench", "experiment"],
            "ensaio_clinico_randomizado": ["randomiz", "rct", "ensaio clinico"],
            "quase_experimental": ["quase", "quasi", "antes e depois", "before-after", "pre-post"],
            "coorte": ["coorte", "cohort", "longitudinal"],
            "caso_controle": ["caso-controle", "case-control", "caso controle"],
            "transversal": ["transvers", "cross-section", "survey", "levantamento"],
            "campo_observacional": ["campo", "field", "monitoramento", "monitoring", "observacional", "observational"],
        }
    },
    "aliases_pais": {
        "brasil": "Brasil", "brazil": "Brasil",
        "eua": "Estados Unidos", "usa": "Estados Unidos", "united states": "Estados Unidos",
        "estados unidos": "Estados Unidos", "us": "Estados Unidos",
        "uk": "Reino Unido", "united kingdom": "Reino Unido", "england": "Reino Unido",
        "china": "China", "india": "Índia", "índia": "Índia", "spain": "Espanha",
        "espanha": "Espanha", "mexico": "México", "méxico": "México", "portugal": "Portugal",
        "germany": "Alemanha", "alemanha": "Alemanha", "italy": "Itália", "itália": "Itália",
        "france": "França", "frança": "França", "iran": "Irã", "irã": "Irã",
    },
    "dimensoes_mapa_evidencias": ["agrupamento_desfecho", "matriz_harm"],
    "criterios_metanalise": {
        "k_minimo": 3,
        "exigir_dispersao": True,
        "exigir_n": True,
        "exigir_unidade_comum": True,
        "exigir_mesmo_tipo_medida": True,
    },
    "associacoes": {"n_minimo": 5, "alfa": 0.05, "n_minimo_por_grupo": 2},
    "qualidade": {
        "checklist_padrao": "transversal_analitico",
        "cortes_percentuais": {"alta": 70, "moderada": 50},
        "respostas_validas": ["Sim", "Não", "Incerto", "Não se aplica"],
    },
    "figuras": {"dpi": 600, "formato_extra": "tiff", "largura_max_celula_painel_px": 3600},
}

def carregar_esquema(caminho: str | Path | None = None) -> dict:
    esquema = copy.deepcopy(ESQUEMA_PADRAO)
    if caminho:
        usuario = json.loads(Path(caminho).read_text(encoding="utf-8"))
        for chave, valor in usuario.items():
            if isinstance(valor, dict) and isinstance(esquema.get(chave), dict) and chave not in (
                "agrupamentos_desfecho", "variaveis_fisicoquimicas", "campos_estudo"
            ):
                esquema[chave].update(valor)
            else:
                esquema[chave] = valor
    return esquema

def salvar_esquema_modelo(caminho: str | Path) -> Path:
    caminho = Path(caminho)
    caminho.write_text(json.dumps(ESQUEMA_PADRAO, ensure_ascii=False, indent=2), encoding="utf-8")
    return caminho


# Reading
"""Transforma campos de texto"""

_AUSENTES = {
    "", "na", "n/a", "nr", "n.r.", "nan", "none", "null", "-", "—", "–", "?",
    "nao relatado", "não relatado", "not reported", "nao informado", "não informado",
    "nao se aplica", "não se aplica", "not applicable",
}
_NAO_DETECTADO = re.compile(
    r"^(n\.?\s?d\.?|nao detectado|não detectado|not detected|bdl|below detection limit|"
    r"<\s*l\.?o\.?d\.?|<\s*l\.?d\.?|<\s*l\.?o\.?q\.?|<\s*l\.?q\.?)$",
    re.IGNORECASE,
)
_NUM = r"[-+]?\d+(?:[.,]\d+)*(?:\s*[x×]\s*10\s*\^?\s*[-+]?\d+|[eE][-+]?\d+)?"

def sem_acento(texto) -> str:
    texto = "" if texto is None else str(texto)
    return "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)).lower().strip()

def _vazio(valor) -> bool:
    if valor is None:
        return True
    if isinstance(valor, float) and np.isnan(valor):
        return True
    try:
        if pd.isna(valor):
            return True
    except (TypeError, ValueError):
        pass
    return str(valor).strip().lower() in _AUSENTES

def _para_float(token: str) -> tuple[float | None, list[str]]:
    flags: list[str] = []
    s = token.strip().replace("−", "-").replace(" ", "")
    m = re.fullmatch(r"([-+]?\d+(?:[.,]\d+)?)[x×]10\^?([-+]?\d+)", s)
    if m:
        return float(m.group(1).replace(",", ".")) * 10 ** int(m.group(2)), flags
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        if re.fullmatch(r"[-+]?\d{1,3},\d{3}", s):
            flags.append("virgula_ambigua(decimal_assumido)")
        if s.count(",") > 1:
            s = s.replace(",", "")
            flags.append("virgulas_milhar_removidas")
        else:
            s = s.replace(",", ".")
    try:
        return float(s), flags
    except ValueError:
        return None, flags + ["numero_nao_interpretavel"]

def interpretar_valor(texto) -> dict:
    """Converte um campo bruto em componentes numéricos."""

    res = {"central": np.nan, "minimo": np.nan, "maximo": np.nan, "dispersao_pm": np.nan,
           "tipo": "ausente", "qualificador": "", "texto_residual": "", "flags": []}
    if _vazio(texto):
        return res
    bruto = str(texto).strip()
    s = bruto.replace("\u2212", "-").replace("\u00a0", " ")
    s = re.sub(r"^\s*[A-Za-zÀ-ú_ ]{1,15}\s*[=:]\s*(?=[-+<>≤≥~≈]?\s*\d)", "", s)
    if _NAO_DETECTADO.match(s.strip()):
        res.update(tipo="nao_detectado", qualificador="ND")
        return res

    m = re.match(rf"^\s*({_NUM})\s*(?:±|\+/-|\+-)\s*({_NUM})(.*)$", s)
    if m:
        c, f1 = _para_float(m.group(1))
        d, f2 = _para_float(m.group(2))
        res.update(central=c, dispersao_pm=d, tipo="media_pm", texto_residual=m.group(3).strip())
        res["flags"] += f1 + f2 + ["pm_sem_especificacao(DP_ou_EP?)"]
        return res

    m = re.match(rf"^\s*({_NUM})\s*(?:-|–|—|a|to|até|ate)\s*({_NUM})(.*)$", s, flags=re.IGNORECASE)
    if m:
        a, f1 = _para_float(m.group(1))
        b, f2 = _para_float(m.group(2))
        if a is not None and b is not None:
            lo, hi = min(a, b), max(a, b)
            res.update(minimo=lo, maximo=hi, central=(lo + hi) / 2, tipo="intervalo",
                       texto_residual=m.group(3).strip())
            res["flags"] += f1 + f2 + ["central=ponto_medio_do_intervalo"]
            return res

    m = re.match(rf"^\s*([<>≤≥]=?)\s*({_NUM})(.*)$", s)
    if m:
        v, f1 = _para_float(m.group(2))
        res.update(central=v, tipo="censurado", qualificador=m.group(1), texto_residual=m.group(3).strip())
        res["flags"] += f1 + ["valor_censurado"]
        return res

    m = re.match(rf"^\s*[~≈]?\s*({_NUM})(.*)$", s)
    if m:
        v, f1 = _para_float(m.group(1))
        res.update(central=v, minimo=v, maximo=v, tipo="pontual", texto_residual=m.group(2).strip())
        res["flags"] += f1
        if v is None:
            res["tipo"] = "nao_interpretavel"
        return res

    res.update(tipo="nao_interpretavel")
    res["flags"].append("texto_sem_numero")
    return res

def para_inteiro(texto) -> float:
    r = interpretar_valor(texto)
    v = r["central"]
    return float(round(v)) if v is not None and not pd.isna(v) else np.nan


# Conersão Unidades
_UNIDADES = {
    "": ("", "adimensional", 1.0, 0.0),
    "°c": ("°C", "temperatura", 1.0, 0.0), "c": ("°C", "temperatura", 1.0, 0.0),
    "oc": ("°C", "temperatura", 1.0, 0.0), "celsius": ("°C", "temperatura", 1.0, 0.0),
    "k": ("K", "temperatura", 1.0, -273.15), "kelvin": ("K", "temperatura", 1.0, -273.15),
    "°f": ("°F", "temperatura", 5 / 9, -32 * 5 / 9), "f": ("°F", "temperatura", 5 / 9, -32 * 5 / 9),
    "s": ("s", "tempo", 1 / 3600, 0.0), "seg": ("s", "tempo", 1 / 3600, 0.0),
    "min": ("min", "tempo", 1 / 60, 0.0), "minutos": ("min", "tempo", 1 / 60, 0.0),
    "h": ("h", "tempo", 1.0, 0.0), "hr": ("h", "tempo", 1.0, 0.0), "horas": ("h", "tempo", 1.0, 0.0),
    "hora": ("h", "tempo", 1.0, 0.0), "hours": ("h", "tempo", 1.0, 0.0),
    "d": ("d", "tempo", 24.0, 0.0), "dia": ("d", "tempo", 24.0, 0.0), "dias": ("d", "tempo", 24.0, 0.0),
    "day": ("d", "tempo", 24.0, 0.0), "days": ("d", "tempo", 24.0, 0.0),
    "semana": ("semana", "tempo", 168.0, 0.0), "semanas": ("semana", "tempo", 168.0, 0.0),
    "week": ("semana", "tempo", 168.0, 0.0), "weeks": ("semana", "tempo", 168.0, 0.0),
    "ng/l": ("ng/L", "concentracao_massa", 1e-6, 0.0),
    "µg/l": ("µg/L", "concentracao_massa", 1e-3, 0.0), "ug/l": ("µg/L", "concentracao_massa", 1e-3, 0.0),
    "mg/l": ("mg/L", "concentracao_massa", 1.0, 0.0), "mg/dm3": ("mg/L", "concentracao_massa", 1.0, 0.0),
    "g/l": ("g/L", "concentracao_massa", 1e3, 0.0),
    "mg/ml": ("mg/mL", "concentracao_massa", 1e3, 0.0),
    "µg/ml": ("µg/mL", "concentracao_massa", 1.0, 0.0), "ug/ml": ("µg/mL", "concentracao_massa", 1.0, 0.0),
    "ppm": ("ppm", "concentracao_massa", 1.0, 0.0), "ppb": ("ppb", "concentracao_massa", 1e-3, 0.0),
    "µs/cm": ("µS/cm", "condutividade", 1.0, 0.0), "us/cm": ("µS/cm", "condutividade", 1.0, 0.0),
    "ms/cm": ("mS/cm", "condutividade", 1e3, 0.0), "ds/m": ("dS/m", "condutividade", 1e3, 0.0),
    "s/m": ("S/m", "condutividade", 1e4, 0.0),
    "%": ("%", "fracao", 1.0, 0.0), "percent": ("%", "fracao", 1.0, 0.0),
}
UNIDADE_ALVO = {
    "adimensional": "", "temperatura": "°C", "tempo": "h", "concentracao_massa": "mg/L",
    "condutividade": "µS/cm", "fracao": "%",
}
_AVISO_UNIDADE = {"ppm": "ppm≈mg/L (assume meio aquoso)", "ppb": "ppb≈µg/L (assume meio aquoso)"}

def chave_unidade(unidade) -> str:
    if _vazio(unidade):
        return ""
    s = str(unidade).strip().replace("μ", "µ").replace("º", "°").replace("˚", "°").lower()
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[.·*]?(l|ml|cm|m|kg|g|dm3)(?:-1|\^-1|⁻¹)$", r"/\1", s)
    s = s.replace("·", "").replace("*", "")
    s = re.sub(r"^(\w+)\.(?=/)", r"\1", s)
    return s

def converter_unidade(valor: float, unidade_bruta, dimensao_esperada: str | None = None, *, dispersao=False):
    flags = []
    chave = chave_unidade(unidade_bruta)
    info = _UNIDADES.get(chave)
    if info is None:
        flags.append(f"unidade_nao_reconhecida:{unidade_bruta}")
        return (valor, str(unidade_bruta).strip() if not _vazio(unidade_bruta) else "", chave, flags)
    exib, dim, escala, desloc = info
    if dimensao_esperada and dim != dimensao_esperada:
        if not (dim == "adimensional" and dimensao_esperada == "adimensional"):
            flags.append(f"dimensao_incompativel:{dim}≠{dimensao_esperada}")
            return (valor, exib, chave, flags)
    if chave in _AVISO_UNIDADE:
        flags.append(_AVISO_UNIDADE[chave])
    if valor is None or pd.isna(valor):
        return (np.nan, UNIDADE_ALVO[dim], chave, flags)
    convertido = valor * abs(escala) if dispersao else valor * escala + desloc
    if exib != UNIDADE_ALVO[dim]:
        flags.append(f"convertido:{exib}->{UNIDADE_ALVO[dim]}")
    return (convertido, UNIDADE_ALVO[dim], chave, flags)

def _dimensao_da_unidade(unidade) -> str | None:
    info = _UNIDADES.get(chave_unidade(unidade))
    return info[1] if info else None

def classificar_por_palavras(texto, mapa: dict[str, list[str]], padrao="nao_mapeado") -> tuple[str, list[str]]:
    alvo = sem_acento(texto)
    if not alvo:
        return "ausente", []
    achados = [cat for cat, palavras in mapa.items() if any(sem_acento(p) in alvo for p in palavras)]
    if not achados:
        return padrao, [f"{padrao}:{texto}"]
    flags = [f"multiplas_categorias:{'|'.join(achados)}"] if len(achados) > 1 else []
    return achados[0], flags


# Modelo
"""Cria a planilha de extração em branco e lê as planilhas preenchidas como texto."""

COLUNAS_DESFECHO = [
    "id_estudo", "desfecho", "grupo", "comparador", "tempo_medicao", "tipo_medida", "valor",
    "unidade", "dp", "ep", "ic_inferior", "ic_superior", "n", "direcao_efeito", "pagina",
    "trecho_evidencia", "fonte_extracao", "revisado_por",
]

def colunas_estudo(esquema: dict) -> list[str]:
    cols = ["id_estudo", "arquivo_pdf"] + list(esquema["campos_estudo"])
    for var in esquema["variaveis_fisicoquimicas"]:
        cols += [f"{var}_valor", f"{var}_unidade"]
    return cols + ["trecho_evidencia", "fonte_extracao", "revisado_por", "observacoes"]

def criar_modelo_extracao(caminho: str | Path, esquema: dict, estudos: list[dict] | None = None,
                          desfechos: list[dict] | None = None, falhas: list[dict] | None = None) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    wb.remove(wb["Sheet"])
    cab = Font(bold=True, color="FFFFFF")
    fundo = PatternFill("solid", fgColor="1F4E78")

    def aba(nome, colunas, linhas):
        ws = wb.create_sheet(nome)
        ws.append(colunas)
        for c in ws[1]:
            c.font, c.fill = cab, fundo
            c.alignment = Alignment(wrap_text=True, vertical="top")
        for linha in linhas or []:
            ws.append(["" if linha.get(c) is None or (isinstance(linha.get(c), float) and np.isnan(linha.get(c)))
                       else str(linha.get(c)) for c in colunas])
        for i, col in enumerate(colunas, 1):
            ws.column_dimensions[get_column_letter(i)].width = 45 if "trecho" in col else max(12, min(30, len(col) + 4))
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.number_format = "@"
        ws.freeze_panes = "B2"
        ws.auto_filter.ref = ws.dimensions

    aba("estudos", colunas_estudo(esquema), estudos)
    aba("desfechos", COLUNAS_DESFECHO, desfechos)
    if falhas:
        aba("falhas_extracao", ["arquivo_pdf", "erro"], falhas)
    ws = wb.create_sheet("instrucoes")
    for linha in [
        "Planilha de extração BRUTA — registre os valores exatamente como aparecem no artigo.",
        "Não converta unidades nem calcule nada aqui: a harmonização é feita pelo script, em colunas separadas.",
        "Aba 'desfechos' em formato longo: uma linha por estudo × desfecho × grupo × tempo.",
        "Use 'NR' para não relatado e 'ND' para não detectado. Intervalos como '6,5–7,2'; média±DP como '7,0 ± 0,3'.",
        "fonte_extracao: 'manual', 'llm_nao_revisado' ou 'llm_revisado'. Preencha 'revisado_por' ao conferir.",
        f"Variáveis físico-químicas: {', '.join(esquema['variaveis_fisicoquimicas'])}.",
    ]:
        ws.append([linha])
    ws.column_dimensions["A"].width = 120
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb.save(caminho)
    return caminho

def ler_extracao(caminho: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    estudos = pd.read_excel(caminho, sheet_name="estudos", dtype=str, engine="openpyxl").fillna("")
    desfechos = pd.read_excel(caminho, sheet_name="desfechos", dtype=str, engine="openpyxl").fillna("")
    estudos = estudos[estudos["id_estudo"].str.strip() != ""].reset_index(drop=True)
    desfechos = desfechos[desfechos["id_estudo"].str.strip() != ""].reset_index(drop=True)
    estudos.insert(0, "id_linha", [f"E{i + 1:04d}" for i in range(len(estudos))])
    desfechos.insert(0, "id_linha", [f"D{i + 1:05d}" for i in range(len(desfechos))])
    duplicados = estudos["id_estudo"][estudos["id_estudo"].duplicated()].unique().tolist()
    if duplicados:
        LOGGER.warning("id_estudo duplicado na aba estudos: %s", duplicados)
    orfaos = sorted(set(desfechos["id_estudo"]) - set(estudos["id_estudo"]))
    if orfaos:
        LOGGER.warning("Desfechos sem estudo correspondente: %s", orfaos)
    return estudos, desfechos


# Harmonização (Visual)
def harmonizar_estudos(estudos_brutos: pd.DataFrame, esquema: dict) -> pd.DataFrame:
    df = estudos_brutos.copy()
    flags_por_linha: list[list[str]] = [[] for _ in range(len(df))]

    def col(nome):
        return df[nome] if nome in df else pd.Series([""] * len(df), index=df.index)

    anos = []
    for i, v in enumerate(col("ano")):
        m = re.search(r"(19|20)\d{2}", str(v))
        anos.append(float(m.group(0)) if m else np.nan)
        if not m and not _vazio(v):
            flags_por_linha[i].append(f"ano_nao_interpretavel:{v}")
    df["ano_harm"] = anos

    aliases = {sem_acento(k): v for k, v in esquema.get("aliases_pais", {}).items()}
    paises = []
    for v in col("pais"):
        if _vazio(v):
            paises.append("")
            continue
        partes = [p.strip() for p in re.split(r"[;/,]| e | and ", str(v)) if p.strip()]
        norm = [aliases.get(sem_acento(p), p.strip().title()) for p in partes]
        paises.append("; ".join(dict.fromkeys(norm)))
    df["pais_harm"] = paises
    df["multinacional"] = df["pais_harm"].str.contains(";")

    for campo, mapa in esquema.get("mapeamento_categorias", {}).items():
        resultados = [classificar_por_palavras(v, mapa) for v in col(campo)]
        df[f"{campo}_harm"] = [r[0] for r in resultados]
        for i, (_, fl) in enumerate(resultados):
            flags_por_linha[i] += [f"{campo}:{f}" for f in fl]

    for campo in ("matriz", "tecnica"):
        df[f"{campo}_harm"] = [sem_acento(v).strip(" .;") if not _vazio(v) else "" for v in col(campo)]

    df["n_amostral_harm"] = [para_inteiro(v) for v in col("n_amostral")]

    for var, info in esquema["variaveis_fisicoquimicas"].items():
        dim = info.get("dimensao", "adimensional")
        cent, mn, mx, pm, un, tipo = [], [], [], [], [], []
        for i, (valor, unidade) in enumerate(zip(col(f"{var}_valor"), col(f"{var}_unidade"))):
            r = interpretar_valor(valor)
            fl = [f"{var}:{f}" for f in r["flags"]]
            u = unidade
            if _vazio(u) and r["texto_residual"] and _dimensao_da_unidade(r["texto_residual"]):
                u = r["texto_residual"]
                fl.append(f"{var}:unidade_inferida_do_valor:{u}")
            if r["tipo"] in ("ausente", "nao_detectado", "nao_interpretavel"):
                cent.append(np.nan); mn.append(np.nan); mx.append(np.nan); pm.append(np.nan)
                un.append(UNIDADE_ALVO.get(dim, "")); tipo.append(r["tipo"])
                if r["tipo"] == "nao_interpretavel":
                    fl.append(f"{var}:valor_nao_interpretavel:{valor}")
                flags_por_linha[i] += fl
                continue
            if _vazio(u) and dim not in ("adimensional",):
                fl.append(f"{var}:unidade_ausente(assumida_{UNIDADE_ALVO.get(dim, '')})")
                c, alvo, flc = r["central"], UNIDADE_ALVO.get(dim, ""), []
                a, b, d = r["minimo"], r["maximo"], r["dispersao_pm"]
            else:
                c, alvo, _, flc = converter_unidade(r["central"], u, dim)
                a = converter_unidade(r["minimo"], u, dim)[0]
                b = converter_unidade(r["maximo"], u, dim)[0]
                d = converter_unidade(r["dispersao_pm"], u, dim, dispersao=True)[0]
            if any(f.startswith(("dimensao_incompativel", "unidade_nao_reconhecida")) for f in flc):
                c = a = b = d = np.nan
            cent.append(c); mn.append(a); mx.append(b); pm.append(d); un.append(alvo); tipo.append(r["tipo"])
            flags_por_linha[i] += fl + [f"{var}:{f}" for f in flc]
        df[f"{var}_central"], df[f"{var}_min"], df[f"{var}_max"] = cent, mn, mx
        df[f"{var}_pm"], df[f"{var}_unidade_harm"], df[f"{var}_tipo_valor"] = pm, un, tipo

    df["flags_harmonizacao"] = [" | ".join(f) for f in flags_por_linha]
    df["excluido"] = False
    return df

def _derivar_dp(dp, ep, ic_inf, ic_sup, n) -> tuple[float, str]:
    if not pd.isna(dp):
        return dp, "relatado"
    if not pd.isna(ep) and not pd.isna(n) and n > 0:
        return ep * np.sqrt(n), "derivado_EP×√n"
    if not pd.isna(ic_inf) and not pd.isna(ic_sup) and not pd.isna(n) and n > 1:
        t = stats.t.ppf(0.975, n - 1) if n < 60 else 1.959964
        return np.sqrt(n) * (ic_sup - ic_inf) / (2 * t), ("derivado_IC95_t" if n < 60 else "derivado_IC95_z")
    return np.nan, "ausente"

def harmonizar_desfechos(desfechos_brutos: pd.DataFrame, esquema: dict) -> pd.DataFrame:
    df = desfechos_brutos.copy()
    for c in COLUNAS_DESFECHO:
        if c not in df:
            df[c] = ""
    linhas = []
    for _, row in df.iterrows():
        fl: list[str] = []
        r = interpretar_valor(row["valor"])
        fl += [f"valor:{f}" for f in r["flags"]]
        unidade_bruta = row["unidade"]
        if _vazio(unidade_bruta) and r["texto_residual"]:
            unidade_bruta = r["texto_residual"]
            fl.append(f"unidade_inferida_do_valor:{unidade_bruta}")

        dp = interpretar_valor(row["dp"])["central"]
        ep = interpretar_valor(row["ep"])["central"]
        ic_inf = interpretar_valor(row["ic_inferior"])["central"]
        ic_sup = interpretar_valor(row["ic_superior"])["central"]
        n = para_inteiro(row["n"])
        dp_de_pm = False
        if pd.isna(dp) and not pd.isna(r["dispersao_pm"]):
            tipo_med = sem_acento(row["tipo_medida"])
            if "ep" in tipo_med.split() or "erro padrao" in tipo_med or "sem" in tipo_med.split():
                ep = r["dispersao_pm"]
                fl.append("pm_interpretado_como_EP(tipo_medida)")
            else:
                dp = r["dispersao_pm"]
                dp_de_pm = True
                fl.append("pm_assumido_DP")
        dp_final, metodo = _derivar_dp(dp, ep, ic_inf, ic_sup, n)
        if dp_de_pm and metodo == "relatado":
            metodo = "relatado_±(assumido_DP)"

        dim = _dimensao_da_unidade(unidade_bruta)
        if dim:
            v_conv, u_alvo, _, flc = converter_unidade(r["central"], unidade_bruta, dim)
            dp_conv = converter_unidade(dp_final, unidade_bruta, dim, dispersao=True)[0]
        else:
            v_conv, u_alvo, flc = r["central"], (str(unidade_bruta).strip() if not _vazio(unidade_bruta) else ""), []
            dp_conv = dp_final
            if not _vazio(unidade_bruta):
                flc.append(f"unidade_sem_conversao:{unidade_bruta}")
            elif r["tipo"] not in ("ausente",):
                flc.append("unidade_ausente")
        fl += flc
        grupo, flg = classificar_por_palavras(row["desfecho"], esquema["agrupamentos_desfecho"], "nao_classificado")
        fl += flg
        tem_disp = not pd.isna(dp_final)
        linhas.append({
            "valor_tipo": r["tipo"], "valor_qualificador": r["qualificador"],
            "valor_harm": r["central"], "valor_min": r["minimo"], "valor_max": r["maximo"],
            "dp_harm": dp_final, "dp_metodo": metodo, "ep_harm": ep, "ic_inf_harm": ic_inf,
            "ic_sup_harm": ic_sup, "n_harm": n, "unidade_harm": u_alvo,
            "valor_conv": v_conv, "dp_conv": dp_conv, "agrupamento_desfecho": grupo,
            "tipo_medida_harm": sem_acento(row["tipo_medida"]) or "nao_informado",
            "tem_dispersao": tem_disp, "tem_n": not pd.isna(n),
            "tem_valor": not pd.isna(r["central"]),
            "dados_completos_ma": (not pd.isna(r["central"])) and tem_disp and not pd.isna(n),
            "flags_harmonizacao": " | ".join(fl), "excluido": False,
        })
    return pd.concat([df.reset_index(drop=True), pd.DataFrame(linhas)], axis=1)


# Revisão Manual (Flags/Alertas)
"""Lista os itens que pedem revisão manual."""

_FLAGS_PARA_REVISAO = ("nao_interpretavel", "ambigua", "nao_reconhecida", "incompativel", "nao_classificado",
                       "nao_mapeado", "multiplas_categorias", "pm_assumido", "unidade_ausente", "inferida")

def listar_pendencias(estudos_h: pd.DataFrame, desfechos_h: pd.DataFrame) -> pd.DataFrame:
    pend = []
    for nivel, df in (("estudo", estudos_h), ("desfecho", desfechos_h)):
        for _, row in df.iterrows():
            for flag in [f.strip() for f in str(row["flags_harmonizacao"]).split("|") if f.strip()]:
                if any(k in flag for k in _FLAGS_PARA_REVISAO):
                    pend.append({"nivel": nivel, "id_linha": row["id_linha"], "id_estudo": row["id_estudo"],
                                 "contexto": row.get("desfecho", "") if nivel == "desfecho" else row.get("titulo", ""),
                                 "motivo": flag})
    out = pd.DataFrame(pend, columns=["nivel", "id_linha", "id_estudo", "contexto", "motivo"])
    out.insert(0, "id_pendencia", [f"P{i + 1:05d}" for i in range(len(out))])
    return out

def criar_modelo_revisao_manual(pendencias: pd.DataFrame, caminho: str | Path) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "correcoes"
    dv = DataValidation(type="list", formula1='"manter,corrigir,excluir_linha"', allow_blank=True)
    colunas = list(pendencias.columns) + ["decisao", "campo_harmonizado", "valor_corrigido","revisor", "data", "justificativa"]
    ws.append(colunas)
    for c in ws[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="7F3F00")
    for _, r in pendencias.iterrows():
        ws.append([str(r[c]) for c in pendencias.columns] + [""] * 6)
    dv = DataValidation(type="list", formula1='"manter,corrigir,excluir_linha"', allow_blank=True)
    ws.add_data_validation(dv)
    col_dec = colunas.index("decisao") + 1
    letra = get_column_letter(col_dec)
    dv.add(f"{letra}2:{letra}{max(len(pendencias) + 200, 500)}")
    for letra_c, larg in zip("ABCDEFGHIJKL", (11, 10, 10, 12, 40, 50, 14, 24, 18, 14, 12, 40)):
        ws.column_dimensions[letra_c].width = larg
    ws.freeze_panes = "B2"
    info = wb.create_sheet("instrucoes")
    for t in [
        "decisao = manter (aceita a harmonização automática), corrigir ou excluir_linha.",
        "Para 'corrigir', informe campo_harmonizado (ex.: valor_conv, unidade_harm, agrupamento_desfecho, "
        "ph_central, desenho_estudo_harm) e valor_corrigido.",
        "Os dados brutos nunca são alterados; as correções são aplicadas apenas às colunas harmonizadas e registradas em log.",
        "Reexecute: python -m article_reader analisar executar --extracao ... --correcoes este_arquivo.xlsx",
    ]:
        info.append([t])
    info.column_dimensions["A"].width = 120
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb.save(caminho)
    return caminho

def aplicar_correcoes(estudos_h, desfechos_h, caminho_correcoes) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    corr = pd.read_excel(caminho_correcoes, sheet_name="correcoes", dtype=str, engine="openpyxl").fillna("")
    corr = corr[corr["decisao"].isin(["corrigir", "excluir_linha"])]
    log = []
    tabelas = {"E": estudos_h.copy(), "D": desfechos_h.copy()}
    for _, c in corr.iterrows():
        df = tabelas[c["id_linha"][0]]
        mask = df["id_linha"] == c["id_linha"]
        if not mask.any():
            log.append({**c.to_dict(), "status": "id_linha_inexistente"})
            continue
        if c["decisao"] == "excluir_linha":
            df.loc[mask, "excluido"] = True
            log.append({**c.to_dict(), "valor_anterior": "", "status": "aplicada"})
            continue
        campo = c["campo_harmonizado"].strip()
        protegido = campo in colunas_brutas_protegidas() or campo.endswith(("_valor", "_unidade"))
        if campo not in df or protegido:
            log.append({**c.to_dict(), "status": "campo_invalido_ou_bruto_protegido"})
            continue
        anterior = df.loc[mask, campo].iloc[0]
        novo = c["valor_corrigido"]
        if pd.api.types.is_numeric_dtype(df[campo]):
            novo = interpretar_valor(novo)["central"]
        df.loc[mask, campo] = novo
        df.loc[mask, "flags_harmonizacao"] = df.loc[mask, "flags_harmonizacao"] + f" | corrigido_manual:{campo}"
        log.append({**c.to_dict(), "valor_anterior": str(anterior), "status": "aplicada"})
    d = tabelas["D"]
    d["tem_valor"] = d["valor_harm"].notna()
    d["tem_dispersao"] = d["dp_harm"].notna()
    d["tem_n"] = d["n_harm"].notna()
    d["dados_completos_ma"] = d["tem_valor"] & d["tem_dispersao"] & d["tem_n"]
    return tabelas["E"], d, pd.DataFrame(log)

def colunas_brutas_protegidas() -> list[str]:
    return COLUNAS_DESFECHO + [str(k) for k in ESQUEMA_PADRAO["campos_estudo"]] + ["id_estudo", "id_linha"]


# Estatística
def auditoria_faltantes(estudos_h, desfechos_h, esquema) -> tuple[pd.DataFrame, pd.DataFrame]:
    linhas = []
    est = estudos_h[~estudos_h["excluido"]]
    des = desfechos_h[~desfechos_h["excluido"]]
    for v in esquema["variaveis_estudo_criticas"]:
        if v in est:
            aus = est[v].map(_vazio)
            linhas.append(("estudo", "variavel_estudo", v, len(est), int(aus.sum())))
    for v in esquema["variaveis_fisicoquimicas"]:
        aus = est[f"{v}_central"].isna()
        linhas.append(("estudo", "fisicoquimica", v, len(est), int(aus.sum())))
    for v in esquema["variaveis_ensaio_criticas"]:
        if v in des:
            aus = des[v].map(_vazio)
            linhas.append(("desfecho", "ensaio", v, len(des), int(aus.sum())))
    for v, rot in (("tem_dispersao", "dispersao_disponivel(DP_relatado_ou_derivavel)"),
                   ("tem_n", "n_disponivel"), ("dados_completos_ma", "dados_completos_para_MA")):
        linhas.append(("desfecho", "derivada", rot, len(des), int((~des[v].astype(bool)).sum())))
    aud = pd.DataFrame(linhas, columns=["nivel", "tipo", "variavel", "n_total", "n_ausente"])
    aud["pct_ausente"] = (100 * aud["n_ausente"] / aud["n_total"].replace(0, np.nan)).round(1)
    aud["n_estudos_afetados"] = np.nan
    for i, r in aud[aud["nivel"] == "desfecho"].iterrows():
        col = {"dispersao_disponivel(DP_relatado_ou_derivavel)": "tem_dispersao", "n_disponivel": "tem_n",
               "dados_completos_para_MA": "dados_completos_ma"}.get(r["variavel"])
        if col:
            sem = des.groupby("id_estudo")[col].apply(lambda s: not s.astype(bool).any())
        else:
            sem = des.groupby("id_estudo")[r["variavel"]].apply(lambda s: s.map(_vazio).all())
        aud.loc[i, "n_estudos_afetados"] = int(sem.sum())

    mat = pd.DataFrame(index=est["id_estudo"])
    for v in esquema["variaveis_estudo_criticas"]:
        if v in est:
            mat[v] = (~est[v].map(_vazio)).astype(int).values
    for v in esquema["variaveis_fisicoquimicas"]:
        mat[v] = est[f"{v}_central"].notna().astype(int).values
    g = des.groupby("id_estudo")
    for col, rot in (("tem_dispersao", "dispersão"), ("tem_n", "n (ensaio)")):
        mat[rot] = g[col].any().reindex(mat.index).fillna(False).astype(int)
    return aud, mat

def descritivas(estudos_h, desfechos_h, esquema) -> tuple[pd.DataFrame, pd.DataFrame]:
    est = estudos_h[~estudos_h["excluido"]]
    cat = []
    for v in ["ano_harm", "pais_harm", "desenho_estudo_harm", "matriz_harm", "tecnica_harm"]:
        if v not in est:
            continue
        serie = est[v]
        if v == "pais_harm":
            serie = serie.str.split("; ").explode()
        serie = serie.replace("", "não informado").fillna("não informado")
        if v == "ano_harm":
            serie = serie.map(lambda x: str(int(x)) if isinstance(x, (int, float)) and not pd.isna(x) else str(x))
        cont = serie.value_counts()
        for k, n in cont.items():
            cat.append({"variavel": v, "categoria": k, "n_estudos": int(n),
                        "pct_estudos": round(100 * n / len(est), 1)})
    cat_df = pd.DataFrame(cat)
    des = desfechos_h[~desfechos_h["excluido"]]
    for k, n in des.groupby("agrupamento_desfecho")["id_estudo"].nunique().items():
        cat_df = pd.concat([cat_df, pd.DataFrame([{"variavel": "agrupamento_desfecho", "categoria": k,
                                                   "n_estudos": int(n),
                                                   "pct_estudos": round(100 * n / len(est), 1)}])],
                           ignore_index=True)
    num = []
    numericas = {"ano_harm": "ano", "n_amostral_harm": "n_amostral"}
    numericas.update({f"{v}_central": f"{v} ({est[f'{v}_unidade_harm'].iloc[0] if len(est) else ''})"
                      for v in esquema["variaveis_fisicoquimicas"]})
    for col, rot in numericas.items():
        x = pd.to_numeric(est[col], errors="coerce").dropna()
        num.append({"variavel": rot, "n": len(x), "media": x.mean(), "dp": x.std(ddof=1),
                    "mediana": x.median(), "q1": x.quantile(0.25), "q3": x.quantile(0.75),
                    "min": x.min(), "max": x.max()})
    return cat_df, pd.DataFrame(num).round(4)

def resumo_fisicoquimico(estudos_h, esquema) -> pd.DataFrame:
    est = estudos_h[~estudos_h["excluido"]]
    out = []
    for v, info in esquema["variaveis_fisicoquimicas"].items():
        x = est[f"{v}_central"].dropna()
        tipos = est[f"{v}_tipo_valor"].value_counts().to_dict()
        out.append({
            "variavel": info.get("rotulo", v), "unidade_harmonizada": UNIDADE_ALVO.get(info.get("dimensao"), ""),
            "n_estudos_com_dado": len(x), "pct_estudos_com_dado": round(100 * len(x) / max(len(est), 1), 1),
            "mediana": x.median(), "q1": x.quantile(0.25), "q3": x.quantile(0.75),
            "min_relatado": est[f"{v}_min"].min(), "max_relatado": est[f"{v}_max"].max(),
            "n_relatado_como_intervalo": tipos.get("intervalo", 0),
            "n_media_pm": tipos.get("media_pm", 0), "n_nao_detectado": tipos.get("nao_detectado", 0),
            "n_nao_interpretavel": tipos.get("nao_interpretavel", 0),
        })
    return pd.DataFrame(out).round(4)

def _unidade_predominante(serie: pd.Series) -> str:
    s = serie[serie.astype(str) != ""]
    return s.mode().iloc[0] if len(s) else ""

def resumo_agrupamentos(desfechos_h) -> pd.DataFrame:
    des = desfechos_h[~desfechos_h["excluido"]]
    out = []
    for grupo, g in des.groupby("agrupamento_desfecho"):
        u = _unidade_predominante(g["unidade_harm"])
        gu = g[(g["unidade_harm"] == u) & g["valor_conv"].notna()]
        direc = g["direcao_efeito"].replace("", "não relatada").value_counts().to_dict()
        out.append({
            "agrupamento_desfecho": grupo, "n_estudos": g["id_estudo"].nunique(), "n_resultados": len(g),
            "n_desfechos_distintos": g["desfecho"].str.lower().nunique(),
            "unidades_distintas": "; ".join(sorted(set(g["unidade_harm"]) - {""})) or "—",
            "tipos_medida": "; ".join(sorted(set(g["tipo_medida_harm"]))),
            "pct_com_dispersao": round(100 * g["tem_dispersao"].mean(), 1),
            "pct_com_n": round(100 * g["tem_n"].mean(), 1),
            "unidade_predominante": u or "—",
            "mediana_unid_predominante": gu["valor_conv"].median(),
            "iiq_unid_predominante": gu["valor_conv"].quantile(0.75) - gu["valor_conv"].quantile(0.25),
            "direcoes_relatadas": "; ".join(f"{k}: {v}" for k, v in direc.items()),
        })
    return pd.DataFrame(out).sort_values("n_estudos", ascending=False).round(4)

def mapa_evidencias(estudos_h, desfechos_h, esquema) -> tuple[pd.DataFrame, pd.DataFrame]:
    d1, d2 = esquema["dimensoes_mapa_evidencias"]
    base = desfechos_h[~desfechos_h["excluido"]].merge(
        estudos_h[~estudos_h["excluido"]].drop(columns=[c for c in desfechos_h.columns
                                                        if c in estudos_h.columns and c != "id_estudo"]),
        on="id_estudo", how="left")
    for d in (d1, d2):
        base[d] = base[d].replace("", "não informado").fillna("não informado")
    lista = (base.groupby([d1, d2]).agg(n_estudos=("id_estudo", "nunique"), n_resultados=("id_estudo", "size"),
                                         estudos=("id_estudo", lambda s: "; ".join(sorted(set(s)))),
                                         pct_resultados_completos_ma=("dados_completos_ma",
                                                                      lambda s: round(100 * s.mean(), 1)))
             .reset_index().sort_values("n_estudos", ascending=False))
    matriz = base.pivot_table(index=d1, columns=d2, values="id_estudo", aggfunc="nunique", fill_value=0)
    return lista, matriz


# Meta-análise e Associação
"""Verifica quais grupos podem ser combinados e testa associações."""

def prontidao_metanalise(estudos_h, desfechos_h, esquema) -> tuple[pd.DataFrame, str]:
    crit = esquema["criterios_metanalise"]
    des = desfechos_h[~desfechos_h["excluido"]].merge(
        estudos_h[["id_estudo", "desenho_estudo_harm"]] if "desenho_estudo_harm" in estudos_h
        else estudos_h[["id_estudo"]], on="id_estudo", how="left")
    out = []
    for grupo, g in des.groupby("agrupamento_desfecho"):
        u = _unidade_predominante(g["unidade_harm"])
        tm = g["tipo_medida_harm"].mode().iloc[0] if len(g) else ""
        elegivel = g.copy()
        if crit["exigir_unidade_comum"]:
            elegivel = elegivel[elegivel["unidade_harm"] == u]
        if crit["exigir_mesmo_tipo_medida"]:
            elegivel = elegivel[elegivel["tipo_medida_harm"] == tm]
        mask = elegivel["tem_valor"].astype(bool)
        if crit["exigir_dispersao"]:
            mask &= elegivel["tem_dispersao"].astype(bool)
        if crit["exigir_n"]:
            mask &= elegivel["tem_n"].astype(bool)
        k_comp = elegivel[mask]["id_estudo"].nunique()
        motivos = []
        if k_comp < crit["k_minimo"]:
            motivos.append(f"k_completos={k_comp} < {crit['k_minimo']}")
        if g["unidade_harm"].replace("", np.nan).nunique() > 1:
            motivos.append("unidades heterogêneas")
        if g["tipo_medida_harm"].nunique() > 1:
            motivos.append("tipos de medida heterogêneos")
        if "desenho_estudo_harm" in g and g["desenho_estudo_harm"].nunique() > 1:
            motivos.append("desenhos de estudo heterogêneos")
        sem_disp = g.groupby("id_estudo")["tem_dispersao"].any()
        sem_n = g.groupby("id_estudo")["tem_n"].any()
        out.append({
            "agrupamento_desfecho": grupo, "k_estudos": g["id_estudo"].nunique(), "n_resultados": len(g),
            "k_com_valor": g[g["tem_valor"].astype(bool)]["id_estudo"].nunique(),
            "k_com_dispersao": int(sem_disp.sum()), "k_sem_dispersao": int((~sem_disp).sum()),
            "k_com_n": int(sem_n.sum()), "k_sem_n": int((~sem_n).sum()),
            "k_dp_derivado": g[g["dp_metodo"].str.startswith("derivado")]["id_estudo"].nunique(),
            "unidade_referencia": u or "—", "tipo_medida_referencia": tm,
            "k_completos_mesma_unidade_e_medida": k_comp,
            "status": "apto" if k_comp >= crit["k_minimo"] else "não apto",
            "motivos_observacoes": "; ".join(motivos) if motivos else "—",
        })
    tab = pd.DataFrame(out).sort_values("k_estudos", ascending=False)

    d = des
    n_res = len(d)
    pct = lambda m: 100 * m.sum() / max(n_res, 1)  # noqa: E731
    sem_dp_rel = pct(~d["dp_metodo"].str.startswith("relatado"))
    sem_ep = pct(d["ep"].map(_vazio))
    sem_ic = pct(d["ic_inferior"].map(_vazio) | d["ic_superior"].map(_vazio))
    sem_n = pct(~d["tem_n"].astype(bool))
    sem_disp = pct(~d["tem_dispersao"].astype(bool))
    aptos = tab[tab["status"] == "apto"]["agrupamento_desfecho"].tolist()
    texto = (
        f"Dos {n_res} resultados extraídos ({d['id_estudo'].nunique()} estudos), {sem_dp_rel:.1f}% não "
        f"relataram desvio padrão, {sem_ep:.1f}% não relataram erro padrão, {sem_ic:.1f}% não relataram "
        f"intervalo de confiança completo e {sem_n:.1f}% não informaram o tamanho amostral do ensaio. "
        f"Mesmo admitindo a derivação do DP a partir do EP ou do IC95% (Cochrane Handbook, seção 6.5.2), "
        f"{sem_disp:.1f}% dos resultados permaneceram sem medida de dispersão utilizável. "
        f"Considerando o critério de pelo menos {crit['k_minimo']} estudos independentes com valor, "
        f"dispersão e n, na mesma unidade e tipo de medida, "
        + (f"apenas o(s) agrupamento(s) {', '.join(aptos)} atingiram o limiar mínimo; "
           "a decisão sobre metanálise nesses casos deve ponderar a heterogeneidade de desenhos e matrizes."
           if aptos else
           "nenhum agrupamento de desfechos atingiu o limiar mínimo, o que justifica a não realização de "
           "uma metanálise formal e a adoção de síntese narrativa estruturada com estatística exploratória.")
    )
    return tab, texto

def _bh(pvals: pd.Series) -> pd.Series:
    """Correção de Benjamini–Hochberg (FDR)."""
    p = pvals.to_numpy(dtype=float)
    ok = ~np.isnan(p)
    adj = np.full_like(p, np.nan)
    if ok.sum():
        pv = p[ok]
        ordem = np.argsort(pv)
        m = len(pv)
        ranq = pv[ordem] * m / np.arange(1, m + 1)
        ranq = np.minimum.accumulate(ranq[::-1])[::-1]
        tmp = np.empty(m)
        tmp[ordem] = np.minimum(ranq, 1)
        adj[ok] = tmp
    return pd.Series(adj, index=pvals.index)

def associacoes_exploratorias(estudos_h, desfechos_h, esquema) -> pd.DataFrame:
    """Spearman (preditores numéricos) e Kruskal–Wallis/Mann–Whitney (categóricos), com a mediana do desfecho por estudo, na unidade predominante de cada agrupamento."""
    cfg = esquema["associacoes"]
    est = estudos_h[~estudos_h["excluido"]]
    des = desfechos_h[~desfechos_h["excluido"]]
    numericos = {"ano": "ano_harm", "n_amostral": "n_amostral_harm"}
    numericos.update({v: f"{v}_central" for v in esquema["variaveis_fisicoquimicas"]})
    categoricos = {c.replace("_harm", ""): c for c in ("desenho_estudo_harm", "matriz_harm") if c in est}
    out = []
    for grupo, g in des.groupby("agrupamento_desfecho"):
        u = _unidade_predominante(g["unidade_harm"])
        gu = g[(g["unidade_harm"] == u) & g["valor_conv"].notna()]
        y = gu.groupby("id_estudo")["valor_conv"].median().rename("y")
        base = est.set_index("id_estudo").join(y, how="inner")
        for rot, col in numericos.items():
            par = base[[col, "y"]].apply(pd.to_numeric, errors="coerce").dropna()
            reg = {"agrupamento_desfecho": grupo, "unidade_desfecho": u or "—", "preditor": rot,
                   "tipo_preditor": "numérico", "teste": "Spearman", "n_estudos": len(par)}
            if len(par) < cfg["n_minimo"] or par[col].nunique() < 3 or par["y"].nunique() < 3:
                reg.update(status="não testado: n ou variabilidade insuficiente")
            else:
                rho, p = stats.spearmanr(par[col], par["y"])
                reg.update(estatistica=rho, rho_spearman=rho, p_valor=p, status="testado")
            out.append(reg)
        for rot, col in categoricos.items():
            sub = base[[col, "y"]].dropna()
            sub = sub[sub[col].astype(str).str.strip() != ""]
            grupos = {k: v["y"].to_numpy() for k, v in sub.groupby(col) if len(v) >= cfg["n_minimo_por_grupo"]}
            reg = {"agrupamento_desfecho": grupo, "unidade_desfecho": u or "—", "preditor": rot,
                   "tipo_preditor": "categórico", "n_estudos": int(sum(len(v) for v in grupos.values())),
                   "n_grupos": len(grupos)}
            if len(grupos) < 2 or reg["n_estudos"] < cfg["n_minimo"]:
                reg.update(teste="Kruskal–Wallis", status="não testado: grupos ou n insuficientes")
            elif len(grupos) == 2:
                a, b = grupos.values()
                st, p = stats.mannwhitneyu(a, b, alternative="two-sided")
                reg.update(teste="Mann–Whitney U", estatistica=st, p_valor=p, status="testado",
                           correlacao_rank_biserial=1 - 2 * float(st) / (len(a) * len(b))) #type: ignore
            else:
                try:
                    st, p = stats.kruskal(*grupos.values())
                    n_t = reg["n_estudos"]
                    reg.update(teste="Kruskal–Wallis", estatistica=st, p_valor=p, status="testado",
                               epsilon2=(st - len(grupos) + 1) / (n_t - len(grupos)))
                except ValueError as erro:
                    reg.update(teste="Kruskal–Wallis", status=f"não testado: {erro}")
            out.append(reg)
    tab = pd.DataFrame(out)
    if tab.empty:
        return tab
    for c in ("estatistica", "p_valor", "rho_spearman"):
        if c not in tab:
            tab[c] = np.nan
    tab["p_ajustado_BH"] = _bh(tab["p_valor"])
    tab["sinal_exploratorio"] = np.where(tab["p_ajustado_BH"] < cfg["alfa"], "p_BH < α", "")
    tab["nota"] = "Análise exploratória, nível estudo, sem ponderação; não confirmatória."
    return tab.round(5)


# Qualidade Metodológi
CHECKLISTS_JBI: dict[str, list[dict]] = {
    "transversal_analitico": [
        {"id": "Q1", "pergunta": "Os critérios de inclusão da amostra foram claramente definidos?",
         "padroes": [r"inclusion criteria", r"crit[ée]rios? de inclus", r"eligib", r"were included if"]},
        {"id": "Q2", "pergunta": "Os sujeitos/amostras e o cenário do estudo foram descritos em detalhe?",
         "padroes": [r"study (area|site|setting)", r"[áa]rea de estudo", r"sampling (site|point|location)",
                     r"pontos? de coleta", r"located in", r"localizad"]},
        {"id": "Q3", "pergunta": "A exposição foi medida de forma válida e confiável?",
         "padroes": [r"calibrat", r"calibra[çc]", r"validated", r"validad", r"standard method", r"m[ée]todo padr"]},
        {"id": "Q4", "pergunta": "Foram usados critérios objetivos e padronizados para medir a condição?",
         "padroes": [r"\bISO\b", r"\bAPHA\b", r"\bAOAC\b", r"\bASTM\b", r"\bEPA\b", r"standardi[sz]ed", r"padroniz"]},
        {"id": "Q5", "pergunta": "Os fatores de confusão foram identificados?",
         "padroes": [r"confound", r"confus[ãa]o", r"covariat", r"covari[áa]ve"]},
        {"id": "Q6", "pergunta": "Foram adotadas estratégias para lidar com os fatores de confusão?",
         "padroes": [r"adjusted for", r"ajustad", r"multivariat", r"multivariad", r"stratif", r"estratific"]},
        {"id": "Q7", "pergunta": "Os desfechos foram medidos de forma válida e confiável?",
         "padroes": [r"limit of (detection|quantification)", r"limite de (detec|quantifica)", r"\bLOD\b", r"\bLOQ\b",
                     r"recovery", r"recupera[çc]", r"replicat", r"triplicat", r"duplicat", r"reprodutib|reproducib"]},
        {"id": "Q8", "pergunta": "Foi utilizada análise estatística apropriada?",
         "padroes": [r"statistical analys", r"an[áa]lise estat", r"\bANOVA\b", r"t-test", r"teste t",
                     r"regress", r"Tukey", r"Kruskal", r"Mann.Whitney", r"p\s*[<≤=]\s*0[.,]0"]},
    ],
    "quase_experimental": [
        {"id": "Q1", "pergunta": "Está claro qual é a 'causa' e qual é o 'efeito' (sem ambiguidade temporal)?",
         "padroes": [r"before and after", r"antes e depois", r"pre.?treatment", r"pr[ée].?tratamento", r"baseline"]},
        {"id": "Q2", "pergunta": "Os participantes/unidades das comparações eram semelhantes?",
         "padroes": [r"similar", r"semelhant", r"comparable", r"compar[áa]ve", r"homogene"]},
        {"id": "Q3", "pergunta": "Os grupos receberam tratamento/cuidado semelhante além da intervenção?",
         "padroes": [r"same conditions", r"mesmas condi", r"identical", r"id[êe]ntic", r"under the same"]},
        {"id": "Q4", "pergunta": "Havia grupo controle?",
         "padroes": [r"control group", r"grupo controle", r"\bcontrol\b", r"\bcontrole\b", r"blank", r"branco"]},
        {"id": "Q5", "pergunta": "Houve múltiplas medições do desfecho antes e depois da intervenção?",
         "padroes": [r"time points?", r"intervalos de tempo", r"kinetic", r"cin[ée]tic", r"repeated measure", r"medidas repetidas"]},
        {"id": "Q6", "pergunta": "O seguimento foi completo ou as perdas foram descritas e analisadas?",
         "padroes": [r"follow.?up", r"seguimento", r"lost to", r"perdas", r"dropout", r"excluded"]},
        {"id": "Q7", "pergunta": "Os desfechos foram medidos da mesma forma em todas as comparações?",
         "padroes": [r"same (method|procedure|protocol)", r"mesmo (m[ée]todo|procedimento|protocolo)"]},
        {"id": "Q8", "pergunta": "Os desfechos foram medidos de forma confiável?",
         "padroes": [r"calibrat", r"calibra[çc]", r"validat", r"validad", r"replicat", r"triplicat", r"\bLOD\b"]},
        {"id": "Q9", "pergunta": "Foi utilizada análise estatística apropriada?",
         "padroes": [r"statistical analys", r"an[áa]lise estat", r"\bANOVA\b", r"t-test", r"regress", r"Tukey"]},
    ],
    "laboratorial_adaptado": [
        {"id": "L1", "pergunta": "O objetivo e as condições experimentais foram claramente descritos?",
         "padroes": [r"experimental (design|conditions|setup)", r"delineamento", r"condi[çc][õo]es experimentais"]},
        {"id": "L2", "pergunta": "Os materiais/amostras foram caracterizados (origem, preparo)?",
         "padroes": [r"were (obtained|purchased|collected)", r"foram (obtid|adquirid|coletad)", r"sample preparation", r"preparo das amostras"]},
        {"id": "L3", "pergunta": "Houve controles adequados (positivo/negativo/branco)?",
         "padroes": [r"control", r"controle", r"blank", r"branco"]},
        {"id": "L4", "pergunta": "Os ensaios foram replicados e o número de réplicas informado?",
         "padroes": [r"triplicat", r"duplicat", r"replicat", r"r[ée]plica", r"n\s*=\s*\d", r"independent experiments"]},
        {"id": "L5", "pergunta": "O método analítico foi validado ou seguiu norma reconhecida?",
         "padroes": [r"validat", r"validad", r"\bISO\b", r"\bAOAC\b", r"\bAPHA\b", r"\bLOD\b", r"\bLOQ\b", r"calibra"]},
        {"id": "L6", "pergunta": "Os resultados foram relatados com medida de dispersão (DP, EP ou IC)?",
         "padroes": [r"±", r"standard deviation", r"desvio.?padr", r"standard error", r"erro padr", r"confidence interval", r"intervalo de confian"]},
        {"id": "L7", "pergunta": "Foi utilizada análise estatística apropriada?",
         "padroes": [r"statistical analys", r"an[áa]lise estat", r"\bANOVA\b", r"t-test", r"teste t", r"Tukey", r"regress"]},
        {"id": "L8", "pergunta": "Houve aleatorização ou cegamento quando aplicável?",
         "padroes": [r"random", r"aleat", r"blind", r"ceg"]},
        {"id": "L9", "pergunta": "Conflitos de interesse e financiamento foram declarados?",
         "padroes": [r"conflict of interest", r"conflito de interesse", r"competing interest", r"funding", r"financiamento"]},
    ],
}

def extrair_paginas_pymupdf(caminho_pdf: str | Path) -> list[str]:
    import pymupdf

    with pymupdf.open(caminho_pdf) as doc:
        if doc.needs_pass and not doc.authenticate(""):
            raise RuntimeError("PDF protegido por senha.")
        return [pagina.get_text("text") for pagina in doc] #type: ignore

def _antes_das_referencias(paginas: list[str]) -> list[str]:
    """Remove a lista de referências."""
    corte = None
    for i, txt in enumerate(paginas):
        if re.search(r"^\s*(references|refer[êe]ncias|bibliography|literature cited)\s*$", txt,
                     flags=re.IGNORECASE | re.MULTILINE):
            corte = i
    if corte is None:
        return paginas
    txt = paginas[corte]
    m = list(re.finditer(r"^\s*(references|refer[êe]ncias|bibliography|literature cited)\s*$", txt,
                         flags=re.IGNORECASE | re.MULTILINE))[-1]
    return paginas[:corte] + [txt[: m.start()]]

def buscar_evidencias(paginas: list[str], padroes: list[str], max_trechos=3, janela=160) -> list[dict]:
    achados = []
    for num, txt in enumerate(paginas, 1):
        plano = re.sub(r"\s+", " ", txt)
        for padrao in padroes:
            for m in re.finditer(padrao, plano, flags=re.IGNORECASE):
                ini, fim = max(0, m.start() - janela), min(len(plano), m.end() + janela)
                achados.append({"pagina": num, "termo": m.group(0), "trecho": "…" + plano[ini:fim].strip() + "…"})
                if len(achados) >= max_trechos:
                    return achados
                break
    return achados

def avaliar_qualidade_pdfs(caminhos_pdf: list[Path], checklist: str | dict, *, mapa_ids: dict | None = None) -> pd.DataFrame:
    itens = CHECKLISTS_JBI[checklist] if isinstance(checklist, str) else checklist
    nome_check = checklist if isinstance(checklist, str) else "personalizado"
    linhas = []
    for caminho in caminhos_pdf:
        caminho = Path(caminho)
        id_estudo = (mapa_ids or {}).get(caminho.name, caminho.stem)
        try:
            paginas = _antes_das_referencias(extrair_paginas_pymupdf(caminho))
            erro = ""
        except Exception as exc:  # noqa: BLE001
            paginas, erro = [], str(exc)
        if erro or len(re.sub(r"\s+", "", "".join(paginas))) < 300:
            erro = erro or "texto insuficiente (PDF escaneado? aplique OCR)"
        for item in itens:
            ev = buscar_evidencias(paginas, item["padroes"]) if not erro else []
            linhas.append({
                "id_estudo": id_estudo, "arquivo_pdf": caminho.name, "checklist": nome_check,
                "item": item["id"], "pergunta": item["pergunta"],
                "sugestao_automatica": ("Erro: " + erro) if erro else ("Sim?" if ev else "Não/Incerto?"),
                "n_evidencias": len(ev),
                "paginas": ", ".join(str(e["pagina"]) for e in ev),
                "evidencias": "\n".join(f"[p.{e['pagina']}] {e['trecho']}" for e in ev),
            })
    return pd.DataFrame(linhas)

def criar_modelo_qualidade(avaliacao: pd.DataFrame, caminho: str | Path, esquema: dict) -> Path:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "avaliacao"
    colunas = list(avaliacao.columns) + ["avaliador_1", "avaliador_2", "consenso", "justificativa_final"]
    ws.append(colunas)
    for c in ws[1]:
        c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="375623")
    for _, r in avaliacao.iterrows():
        ws.append([str(r[c]) for c in avaliacao.columns] + ["", "", "", ""])
    respostas = ",".join(esquema["qualidade"]["respostas_validas"])
    dv = DataValidation(type="list", formula1=f'"{respostas}"', allow_blank=True)
    ws.add_data_validation(dv)
    for nome in ("avaliador_1", "avaliador_2", "consenso"):
        letra = get_column_letter(colunas.index(nome) + 1)
        dv.add(f"{letra}2:{letra}{len(avaliacao) + 1}")
    larguras = {"pergunta": 50, "evidencias": 80, "justificativa_final": 40}
    for i, nome in enumerate(colunas, 1):
        ws.column_dimensions[get_column_letter(i)].width = larguras.get(nome, 14)
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "F2"
    ws.auto_filter.ref = ws.dimensions
    info = wb.create_sheet("instrucoes")
    for t in [
        "Avaliação da qualidade metodológica adaptada das listas de verificação do JBI.",
        "A coluna 'sugestao_automatica' é apenas pré-preenchimento por busca de termos; a decisão é dos avaliadores.",
        "Dois avaliadores independentes preenchem avaliador_1 e avaliador_2; divergências são resolvidas em 'consenso'.",
        "Itens 'Não se aplica' são excluídos do denominador do escore.",
        f"Categorias: alta ≥ {esquema['qualidade']['cortes_percentuais']['alta']}% de 'Sim'; moderada ≥ "
        f"{esquema['qualidade']['cortes_percentuais']['moderada']}%; baixa abaixo disso.",
    ]:
        info.append([t])
    info.column_dimensions["A"].width = 120
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    wb.save(caminho)
    return caminho

def _kappa(a: pd.Series, b: pd.Series) -> float:
    a, b = a.astype(str), b.astype(str)
    if len(a) == 0:
        return np.nan
    cats = sorted(set(a) | set(b))
    po = (a == b).mean()
    pe = sum((a == c).mean() * (b == c).mean() for c in cats)
    return float((po - pe) / (1 - pe)) if pe < 1 else 1.0

def pontuar_qualidade(caminho_avaliacao: str | Path, esquema: dict) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    av = pd.read_excel(caminho_avaliacao, sheet_name="avaliacao", dtype=str, engine="openpyxl").fillna("")
    validas = set(esquema["qualidade"]["respostas_validas"])

    def final(r):
        if r["consenso"] in validas:
            return r["consenso"]
        if r["avaliador_1"] in validas and r["avaliador_1"] == r["avaliador_2"]:
            return r["avaliador_1"]
        return "pendente"

    av["resposta_final"] = av.apply(final, axis=1)
    duplas = av[av["avaliador_1"].isin(validas) & av["avaliador_2"].isin(validas)]
    concord = {
        "itens_com_dupla_avaliacao": len(duplas),
        "concordancia_percentual": round(100 * (duplas["avaliador_1"] == duplas["avaliador_2"]).mean(), 1)
        if len(duplas) else np.nan,
        "kappa_cohen": round(_kappa(duplas["avaliador_1"], duplas["avaliador_2"]), 3) if len(duplas) else np.nan,
        "itens_pendentes": int((av["resposta_final"] == "pendente").sum()),
    }
    cortes = esquema["qualidade"]["cortes_percentuais"]
    por_estudo = []
    for (ide, chk), g in av.groupby(["id_estudo", "checklist"]):
        aplic = g[~g["resposta_final"].isin(["Não se aplica", "pendente"])]
        n_sim = int((aplic["resposta_final"] == "Sim").sum())
        pct = 100 * n_sim / len(aplic) if len(aplic) else np.nan
        pend = int((g["resposta_final"] == "pendente").sum())
        cat = ("pendente" if pend else "alta" if pct >= cortes["alta"] else
               "moderada" if pct >= cortes["moderada"] else "baixa")
        por_estudo.append({"id_estudo": ide, "checklist": chk, "itens": len(g), "itens_aplicaveis": len(aplic),
                           "n_sim": n_sim, "n_nao": int((aplic["resposta_final"] == "Não").sum()),
                           "n_incerto": int((aplic["resposta_final"] == "Incerto").sum()),
                           "itens_pendentes": pend, "pct_sim": round(pct, 1) if not pd.isna(pct) else np.nan,
                           "qualidade": cat})
    return av, pd.DataFrame(por_estudo), concord


# Imagens
"""Matplot."""

def _estilo():
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.titlesize": 10, "axes.titleweight": "bold",
                         "savefig.bbox": "tight", "figure.dpi": 100})

COR = "#00133B"

def _salvar(fig, caminho_base: Path, esquema) -> Path:
    dpi = esquema["figuras"]["dpi"]
    png = caminho_base.with_suffix(".png")
    fig.savefig(png, dpi=dpi)
    if esquema["figuras"].get("formato_extra") == "tiff":
        fig.savefig(caminho_base.with_suffix(".tiff"), dpi=dpi, pil_kwargs={"compression": "tiff_lzw"})
    plt.close(fig)
    return png

def gerar_figuras(pasta: Path, estudos_h, desfechos_h, matriz_mapa, matriz_faltantes, prontidao,
                  esquema, qualidade_av: pd.DataFrame | None = None) -> dict[str, Path]:
    _estilo()
    pasta.mkdir(parents=True, exist_ok=True)
    figs: dict[str, Path] = {}
    est = estudos_h[~estudos_h["excluido"]]

    anos = est["ano_harm"].dropna().astype(int)
    if len(anos):
        fig, ax = plt.subplots(figsize=(6.5, 3.2))
        cont = anos.value_counts().sort_index()
        todos = range(cont.index.min(), cont.index.max() + 1)
        cont = cont.reindex(todos, fill_value=0)
        ax.bar(cont.index, cont.values, color=COR)
        ax.set_xlabel("Ano de publicação"); ax.set_ylabel("Nº de estudos")
        ax.set_title("Estudos incluídos por ano")
        ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
        ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
        figs["ano"] = _salvar(fig, pasta / "fig_estudos_por_ano", esquema)

    paises = est["pais_harm"].replace("", "não informado").str.split("; ").explode().value_counts().head(15)
    if len(paises):
        fig, ax = plt.subplots(figsize=(6.5, 0.3 * len(paises) + 1))
        ax.barh(paises.index[::-1], paises.values[::-1], color=COR)
        ax.set_xlabel("Nº de estudos"); ax.set_title("Distribuição geográfica (15 países mais frequentes)")
        for y, v in enumerate(paises.values[::-1]):
            ax.text(v, y, f" {v}", va="center", fontsize=8)
        figs["paises"] = _salvar(fig, pasta / "fig_paises", esquema)

    if matriz_mapa is not None and matriz_mapa.size:
        m = matriz_mapa
        fig, ax = plt.subplots(figsize=(max(5, 0.55 * m.shape[1] + 3), max(3, 0.4 * m.shape[0] + 1.5)))
        im = ax.imshow(m.values, cmap="Blues", aspect="auto")
        ax.set_xticks(range(m.shape[1]), [str(c)[:28] for c in m.columns], rotation=45, ha="right")
        ax.set_yticks(range(m.shape[0]), [str(i)[:32] for i in m.index])
        vmax = m.values.max() if m.values.size else 0
        for i in range(m.shape[0]):
            for j in range(m.shape[1]):
                v = m.values[i, j]
                if v:
                    ax.text(j, i, str(int(v)), ha="center", va="center", fontsize=7,
                            color="white" if v > vmax / 2 else "black")
        fig.colorbar(im, ax=ax, label="Nº de estudos", shrink=0.8)
        ax.set_title("Mapa de evidências")
        ax.set_xlabel(esquema["dimensoes_mapa_evidencias"][1]); ax.set_ylabel(esquema["dimensoes_mapa_evidencias"][0])
        figs["mapa"] = _salvar(fig, pasta / "fig_mapa_evidencias", esquema)

    if matriz_faltantes is not None and matriz_faltantes.size:
        mf = matriz_faltantes
        fig, ax = plt.subplots(figsize=(max(5, 0.45 * mf.shape[1] + 2), max(3, 0.09 * mf.shape[0] + 1.5)))
        ax.imshow(mf.values, cmap=matplotlib.colors.ListedColormap(["#201818", COR]), aspect="auto",
                  interpolation="nearest", vmin=0, vmax=1)
        ax.set_xticks(range(mf.shape[1]), mf.columns, rotation=45, ha="right")
        if mf.shape[0] <= 40:
            ax.set_yticks(range(mf.shape[0]), mf.index, fontsize=6)
        else:
            ax.set_yticks([]); ax.set_ylabel(f"Estudos (n = {mf.shape[0]})")
        pct = 100 * (1 - mf.mean())
        for j, p in enumerate(pct):
            ax.text(j, -0.8, f"{p:.0f}%", ha="center", va="bottom", fontsize=7, color="#7F0000")
        ax.set_title("Auditoria de dados faltantes (azul = disponível; % = ausência)", pad=18)
        figs["faltantes"] = _salvar(fig, pasta / "fig_dados_faltantes", esquema)

    vars_fq = [(v, i) for v, i in esquema["variaveis_fisicoquimicas"].items() if est[f"{v}_central"].notna().any()]
    if vars_fq:
        ncol = min(3, len(vars_fq))
        nlin = int(np.ceil(len(vars_fq) / ncol))
        fig, axs = plt.subplots(nlin, ncol, figsize=(2.6 * ncol, 2.6 * nlin), squeeze=False)
        rng = np.random.default_rng(SEMENTE)
        for ax, (v, info) in zip(axs.flat, vars_fq):
            x = est[f"{v}_central"].dropna()
            ax.boxplot(x, widths=0.5, showfliers=False, patch_artist=True,
                       boxprops={"facecolor": "#BDD7EE", "edgecolor": COR}, medianprops={"color": COR})
            ax.scatter(1 + rng.uniform(-0.12, 0.12, len(x)), x, s=8, color=COR, alpha=0.7, zorder=3)
            un = UNIDADE_ALVO.get(info.get("dimensao"), "")
            ax.set_title(f"{info.get('rotulo', v)} (n={len(x)})", fontsize=8)
            ax.set_ylabel(un); ax.set_xticks([])
            pos = x[x > 0]
            if len(pos) == len(x) and len(x) > 1 and pos.max() / pos.min() > 1e3:
                ax.set_yscale("log"); ax.set_ylabel(f"{un} (escala log)")
        for ax in list(axs.flat)[len(vars_fq):]:
            ax.axis("off")
        fig.suptitle("Variáveis físico-químicas relatadas (valor central por estudo)", fontsize=10, fontweight="bold")
        fig.tight_layout()
        figs["fisicoquimicos"] = _salvar(fig, pasta / "fig_fisicoquimicos", esquema)

    if prontidao is not None and len(prontidao):
        p = prontidao.sort_values("k_estudos")
        fig, ax = plt.subplots(figsize=(6.5, 0.35 * len(p) + 1.2))
        comp = p["k_completos_mesma_unidade_e_medida"]
        ax.barh(p["agrupamento_desfecho"], comp, color=COR, label="com valor, dispersão e n (mesma unidade)")
        ax.barh(p["agrupamento_desfecho"], p["k_estudos"] - comp, left=comp, color="#D9D9D9",
                label="dados incompletos/incompatíveis")
        ax.axvline(esquema["criterios_metanalise"]["k_minimo"], ls="--", color="#C00000", lw=1,
                   label=f"k mínimo = {esquema['criterios_metanalise']['k_minimo']}")
        ax.set_xlabel("Nº de estudos"); ax.set_title("Prontidão para meta-análise por agrupamento de desfecho")
        ax.legend(fontsize=7, loc="lower right", frameon=False)
        figs["prontidao"] = _salvar(fig, pasta / "fig_prontidao_metanalise", esquema)

    if qualidade_av is not None and len(qualidade_av):
        q = qualidade_av[qualidade_av["resposta_final"] != "pendente"]
        if len(q):
            ordem = ["Sim", "Não", "Incerto", "Não se aplica"]
            cores = {"Sim": "#548235", "Não": "#C00000", "Incerto": "#FFC000", "Não se aplica": "#A6A6A6"}
            tab = (pd.crosstab(q["item"], q["resposta_final"], normalize="index") * 100).reindex(columns=ordem,
                                                                                                fill_value=0)
            fig, ax = plt.subplots(figsize=(6.5, 0.35 * len(tab) + 1.4))
            esq = np.zeros(len(tab))
            for r in ordem:
                ax.barh(tab.index, tab[r], left=esq, color=cores[r], label=r)
                esq += tab[r].to_numpy()
            ax.invert_yaxis(); ax.set_xlim(0, 100); ax.set_xlabel("% dos estudos")
            ax.set_title("Qualidade metodológica (JBI adaptado) por item")
            ax.legend(ncol=4, fontsize=7, loc="upper center", bbox_to_anchor=(0.5, -0.18), frameon=False)
            figs["qualidade"] = _salvar(fig, pasta / "fig_qualidade_jbi", esquema)
    return figs

def montar_painel(imagens: list[Path], destino: Path, esquema, ncol=2) -> Path:
    dpi = esquema["figuras"]["dpi"]
    larg_max = esquema["figuras"]["largura_max_celula_painel_px"]
    ims = []
    for p in imagens:
        im = Image.open(p).convert("RGB")
        if im.width > larg_max:
            im = im.resize((larg_max, int(im.height * larg_max / im.width)), Image.Resampling.LANCZOS)
        ims.append(im)
    if not ims:
        raise ValueError("Nenhuma imagem para o painel.")
    cw, ch = max(i.width for i in ims), max(i.height for i in ims)
    margem = int(0.04 * cw)
    nlin = int(np.ceil(len(ims) / ncol))
    painel = Image.new("RGB", (ncol * (cw + margem) + margem, nlin * (ch + margem) + margem), "white")
    desenho = ImageDraw.Draw(painel)
    try:
        fonte = ImageFont.truetype(font_manager.findfont("DejaVu Sans:bold"), size=max(24, int(cw * 0.035)))
    except OSError:
        fonte = ImageFont.load_default()
    for k, im in enumerate(ims):
        lin, col = divmod(k, ncol)
        x0, y0 = margem + col * (cw + margem), margem + lin * (ch + margem)
        painel.paste(im, (x0 + (cw - im.width) // 2, y0 + (ch - im.height) // 2))
        desenho.text((x0, y0 - int(margem * 0.2)), chr(65 + k), fill="black", font=fonte)
    destino = destino.with_suffix(".png")
    painel.save(destino, dpi=(dpi, dpi), optimize=True)
    if esquema["figuras"].get("formato_extra") == "tiff":
        painel.save(destino.with_suffix(".tiff"), dpi=(dpi, dpi), compression="tiff_lzw")
    return destino


# Excel
def exportar_excel(abas: dict[str, pd.DataFrame], caminho: Path, index_abas: set[str] | frozenset[str] = frozenset()) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(caminho, engine="xlsxwriter") as wr:
        wb = wr.book
        cab = wb.add_format({"bold": True, "font_color": "white", "bg_color": "#1F4E78", "text_wrap": True,
                             "valign": "top", "border": 1})
        for nome, df in abas.items():
            nome31 = nome[:31]
            idx = nome in index_abas
            df.to_excel(wr, sheet_name=nome31, index=idx)
            ws = wr.sheets[nome31]
            cols = ([df.index.name or ""] if idx else []) + [str(c) for c in df.columns]
            for j, c in enumerate(cols):
                ws.write(0, j, c, cab)
                k = j - (1 if idx else 0)
                if k >= 0 and len(df):
                    q = df.iloc[:200, k].astype(str).str.len().quantile(0.9)
                    tam = 10 if pd.isna(q) else int(q) + 2
                else:
                    tam = 10
                larg = min(60, max(10, len(str(c)) + 2, tam))
                ws.set_column(j, j, larg)
            ws.freeze_panes(1, 1)
            if len(df):
                ws.autofilter(0, 0, len(df), len(cols) - 1)
    return caminho


# Registros
"""Versões de software, hashes de arquivos, log, manifesto e texto de disponibilidade de dados."""

PACOTES_REGISTRADOS = ["pandas", "numpy", "scipy", "matplotlib", "openpyxl", "XlsxWriter", "PyMuPDF",
                       "Pillow", "pypdf"]

def versoes_software() -> dict:
    v = {"python": sys.version.split()[0], "plataforma": platform.platform()}
    for p in PACOTES_REGISTRADOS:
        try:
            v[p] = metadata.version(p)
        except metadata.PackageNotFoundError:
            v[p] = "não instalado"
    return v

def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()

def configurar_log(pasta: Path) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / f"execucao_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    LOGGER.setLevel(logging.INFO)
    for h in list(LOGGER.handlers):
        if not getattr(h, "_persistente", False):
            LOGGER.removeHandler(h)
    fh = logging.FileHandler(arq, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    LOGGER.addHandler(fh)
    if not any(getattr(h, "_persistente", False) for h in LOGGER.handlers):
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(logging.Formatter("%(levelname)s | %(message)s"))
        LOGGER.addHandler(sh)
    return arq

def escrever_manifesto(pasta: Path, entradas: list[Path], parametros: dict, esquema: dict) -> Path:
    saidas = [p for p in sorted(pasta.rglob("*")) if p.is_file() and p.name != "manifesto_execucao.json"]
    man = {
        "gerado_em_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "semente": SEMENTE,
        "software": versoes_software(),
        "parametros": parametros,
        "esquema_sha256": hashlib.sha256(json.dumps(esquema, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        "entradas": [{"arquivo": str(p), "sha256": sha256(p), "bytes": p.stat().st_size} for p in entradas],
        "saidas": [{"arquivo": str(p.relative_to(pasta)), "sha256": sha256(p), "bytes": p.stat().st_size}
                   for p in saidas],
    }
    destino = pasta / "manifesto_execucao.json"
    destino.write_text(json.dumps(man, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    req = "\n".join(f"{k}=={v}" for k, v in man["software"].items()
                    if k in PACOTES_REGISTRADOS and v != "não instalado")
    (pasta / "requirements.txt").write_text(req + "\n", encoding="utf-8")
    return destino

def texto_disponibilidade(versoes: dict, n_estudos: int, n_resultados: int, repositorio: str) -> str:
    return (
        "## Software, reprodutibilidade e disponibilidade de dados\n\n"
        "Todas as etapas de curadoria de dados, análises descritivas, mapeamento de evidências, avaliação de "
        "prontidão para meta-análise, estatísticas exploratórias, geração de figuras e avaliação da qualidade "
        "metodológica foram realizadas utilizando scripts Python reproduzíveis "
        f"(Python {versoes['python']}). As análises utilizaram pandas ({versoes['pandas']}) para manipulação de "
        f"dados, NumPy ({versoes['numpy']}) para operações numéricas, SciPy ({versoes['scipy']}) para testes não "
        f"paramétricos e correlações, matplotlib ({versoes['matplotlib']}) para figuras, openpyxl "
        f"({versoes['openpyxl']}) e XlsxWriter ({versoes['XlsxWriter']}) para saídas em Excel, PyMuPDF "
        f"({versoes['PyMuPDF']}) para extração de texto em PDF durante a avaliação metodológica e Pillow "
        f"({versoes['Pillow']}) para a montagem de figuras em alta resolução. Foram processados {n_estudos} "
        f"estudos e {n_resultados} resultados em formato longo. Os resultados gerados incluíram tabelas "
        "harmonizadas em nível de estudo, tabelas de desfechos em formato longo, mapas de evidências, resumos "
        "físico-químicos, resumos de agrupamentos de desfechos, tabelas de prontidão para meta-análise, "
        "auditorias de dados faltantes, tabelas de associação exploratória, tabelas de avaliação de qualidade "
        "adaptadas ao JBI, modelos de revisão manual e figuras em alta resolução.\n\n"
        "O fluxo de trabalho analítico final seguiu o princípio da auditoria em primeiro lugar. Os campos de "
        "extração brutos foram preservados, as variáveis harmonizadas foram geradas em colunas separadas e todas "
        "as análises subsequentes foram baseadas em scripts reproduzíveis e tabelas exportadas. A ausência de "
        "dados foi explicitamente quantificada para variáveis físico-químicas e de nível de ensaio importantes. "
        "A ausência de desvios padrão, erros padrão, intervalos de confiança ou tamanhos de amostra foi "
        "documentada e usada para justificar a não realização de uma metanálise formal. Todos os conjuntos de "
        "dados, código, estratégias de busca, planilhas de extração, resultados da avaliação de qualidade, "
        "scripts de geração de figuras e registros de análise serão depositados no repositório "
        f"{repositorio}.\n"
    )


# Execute
def executar_analises(caminho_extracao: str | Path, pasta_saida: str | Path, *, esquema: dict,
                      caminho_correcoes: str | Path | None = None,
                      caminho_qualidade: str | Path | None = None,
                      repositorio: str = "[inserir repositório/DOI]") -> dict:
    caminho_extracao = Path(caminho_extracao)
    saida = Path(pasta_saida)
    pastas = {k: saida / k for k in ("01_dados_brutos", "02_harmonizados", "03_tabelas", "04_figuras",
                                     "05_qualidade", "06_revisao_manual", "logs")}
    for p in pastas.values():
        p.mkdir(parents=True, exist_ok=True)
    arq_log = configurar_log(pastas["logs"])
    LOGGER.info("Início da análise | extração=%s", caminho_extracao)
    entradas = [caminho_extracao]

    copia = pastas["01_dados_brutos"] / caminho_extracao.name
    shutil.copy2(caminho_extracao, copia)
    LOGGER.info("Cópia bruta preservada (sha256=%s)", sha256(copia))
    (pastas["01_dados_brutos"] / "esquema_utilizado.json").write_text(
        json.dumps(esquema, ensure_ascii=False, indent=2), encoding="utf-8")

    est_b, des_b = ler_extracao(caminho_extracao)
    LOGGER.info("Lidos %d estudos e %d resultados brutos", len(est_b), len(des_b))

    est_h = harmonizar_estudos(est_b, esquema)
    des_h = harmonizar_desfechos(des_b, esquema)
    log_corr = pd.DataFrame()
    if caminho_correcoes:
        entradas.append(Path(caminho_correcoes))
        est_h, des_h, log_corr = aplicar_correcoes(est_h, des_h, caminho_correcoes)
        LOGGER.info("Correções manuais aplicadas: %d", int((log_corr.get("status") == "aplicada").sum())
                    if len(log_corr) else 0)
    est_h.to_csv(pastas["02_harmonizados"] / "tabela_estudos_harmonizada.csv", index=False, encoding="utf-8-sig")
    des_h.to_csv(pastas["02_harmonizados"] / "tabela_desfechos_formato_longo.csv", index=False, encoding="utf-8-sig")

    pend = listar_pendencias(est_h, des_h)
    pend["status_revisao"] = "pendente"
    if caminho_correcoes:
        dec = pd.read_excel(caminho_correcoes, sheet_name="correcoes", dtype=str, engine="openpyxl").fillna("")
        dec = dec[dec["decisao"].isin(["manter", "corrigir", "excluir_linha"])]
        chave = dict(zip(zip(dec["id_linha"], dec["motivo"]), dec["decisao"]))
        chave.update({(i, "*"): d for i, d in zip(dec["id_linha"], dec["decisao"]) if d == "excluir_linha"})
        pend["status_revisao"] = [
            f"resolvida:{chave.get((i, m)) or chave.get((i, '*'))}" if (chave.get((i, m)) or chave.get((i, "*")))
            else "pendente" for i, m in zip(pend["id_linha"], pend["motivo"])]
    criar_modelo_revisao_manual(pend, pastas["06_revisao_manual"] / "modelo_revisao_manual.xlsx")
    LOGGER.info("Pendências para revisão manual: %d (%d ainda pendentes)", len(pend),
                int((pend["status_revisao"] == "pendente").sum()))

    aud, mat_falt = auditoria_faltantes(est_h, des_h, esquema)
    desc_cat, desc_num = descritivas(est_h, des_h, esquema)
    fq = resumo_fisicoquimico(est_h, esquema)
    agr = resumo_agrupamentos(des_h)
    mapa_l, mapa_m = mapa_evidencias(est_h, des_h, esquema)
    pront, justificativa = prontidao_metanalise(est_h, des_h, esquema)
    assoc = associacoes_exploratorias(est_h, des_h, esquema)
    LOGGER.info("Prontidão MA: %s", pront[["agrupamento_desfecho", "status"]].to_dict("records"))

    qual_av = qual_est = None
    concord = {}
    if caminho_qualidade:
        entradas.append(Path(caminho_qualidade))
        qual_av, qual_est, concord = pontuar_qualidade(caminho_qualidade, esquema)
        exportar_excel({"avaliacao_itens": qual_av, "qualidade_por_estudo": qual_est,
                        "concordancia": pd.DataFrame([concord])},
                       pastas["05_qualidade"] / "avaliacao_qualidade_JBI.xlsx")
        LOGGER.info("Qualidade: %s", concord)

    figs = gerar_figuras(pastas["04_figuras"], est_h, des_h, mapa_m, mat_falt, pront, esquema, qual_av)
    painel_ordem = [figs[k] for k in ("ano", "mapa", "faltantes", "prontidao", "fisicoquimicos", "qualidade")
                    if k in figs]
    if painel_ordem:
        figs["painel"] = montar_painel(painel_ordem, pastas["04_figuras"] / "painel_figuras", esquema)
    LOGGER.info("Figuras geradas: %s", [p.name for p in figs.values()])

    abas = {
        "estudos_harmonizados": est_h, "desfechos_formato_longo": des_h,
        "descritiva_categorica": desc_cat, "descritiva_numerica": desc_num,
        "mapa_evidencias_lista": mapa_l, "mapa_evidencias_matriz": mapa_m,
        "resumo_fisicoquimico": fq, "resumo_agrupamentos": agr,
        "prontidao_metanalise": pront, "auditoria_faltantes": aud,
        "associacoes_exploratorias": assoc, "pendencias_revisao": pend,
    }
    if len(log_corr):
        abas["log_correcoes"] = log_corr
    if qual_est is not None:
        abas["qualidade_por_estudo"] = qual_est
    exportar_excel(abas, pastas["03_tabelas"] / "resultados_revisao.xlsx", index_abas={"mapa_evidencias_matriz"})
    for nome, df in abas.items():
        if nome not in ("estudos_harmonizados", "desfechos_formato_longo"):
            df.to_csv(pastas["03_tabelas"] / f"{nome}.csv", index=(nome == "mapa_evidencias_matriz"),
                      encoding="utf-8-sig")
    (pastas["03_tabelas"] / "justificativa_metanalise.md").write_text(
        "# Justificativa sobre a meta-análise\n\n" + justificativa + "\n", encoding="utf-8")
    versoes = versoes_software()
    (saida / "texto_disponibilidade_dados.md").write_text(
        texto_disponibilidade(versoes, est_h["id_estudo"].nunique(), len(des_h), repositorio), encoding="utf-8")

    LOGGER.info("Fim da análise.")
    escrever_manifesto(saida, entradas, {
        "extracao": str(caminho_extracao), "correcoes": str(caminho_correcoes or ""),
        "qualidade": str(caminho_qualidade or ""), "log": arq_log.name,
    }, esquema)
    return {"pasta": saida, "justificativa": justificativa,
            "pendencias": int((pend["status_revisao"] == "pendente").sum()), "figuras": figs,
            "prontidao": pront, "concordancia": concord}


# Repositório
def montar_repositorio(pasta_resultados: str | Path, destino: str | Path, *, codigo: list[Path],
                       estrategias_busca: str | Path | None = None, extras: list[Path] | None = None,
                       compactar: bool = True, pastas_extras: dict[str, Path] | None = None) -> Path:
    res, dest = Path(pasta_resultados), Path(destino)
    if dest.exists():
        shutil.rmtree(dest)
    estrutura = {
        "dados/brutos": res / "01_dados_brutos",
        "dados/harmonizados": res / "02_harmonizados",
        "resultados/tabelas": res / "03_tabelas",
        "resultados/figuras": res / "04_figuras",
        "resultados/qualidade_JBI": res / "05_qualidade",
        "revisao_manual": res / "06_revisao_manual",
        "registros_analise": res / "logs",
    }
    for alvo, origem in estrutura.items():
        if origem.exists():
            shutil.copytree(origem, dest / alvo)
    (dest / "codigo").mkdir(parents=True, exist_ok=True)
    for c in codigo:
        shutil.copy2(c, dest / "codigo" / Path(c).name)
    for f in ("manifesto_execucao.json", "requirements.txt", "texto_disponibilidade_dados.md"):
        if (res / f).exists():
            shutil.copy2(res / f, dest / f)
    if estrategias_busca:
        eb = Path(estrategias_busca)
        if eb.is_dir():
            shutil.copytree(eb, dest / "estrategias_busca")
        else:
            (dest / "estrategias_busca").mkdir(parents=True, exist_ok=True)
            shutil.copy2(eb, dest / "estrategias_busca" / eb.name)
    else:
        (dest / "estrategias_busca").mkdir(parents=True, exist_ok=True)
        (dest / "estrategias_busca" / "LEIA-ME.txt").write_text(
            "Adicione aqui as strings de busca completas por base (data da busca, filtros, nº de registros).\n",
            encoding="utf-8")
    for e in extras or []:
        shutil.copy2(e, dest / Path(e).name)
    for alvo, origem in (pastas_extras or {}).items():
        origem = Path(origem)
        if origem.is_dir():
            shutil.copytree(origem, dest / alvo, ignore=shutil.ignore_patterns("cache"), dirs_exist_ok=True)
        elif origem.is_file():
            (dest / alvo).mkdir(parents=True, exist_ok=True)
            shutil.copy2(origem, dest / alvo / origem.name)
    v = versoes_software()
    (dest / "README.md").write_text(
        "# Pacote de dados e código — revisão sistemática\n\n"
        "## Estrutura\n"
        "- `dados/brutos/`: planilha de extração original (intocada) e esquema utilizado\n"
        "- `dados/harmonizados/`: tabela de estudos harmonizada e tabela de desfechos em formato longo\n"
        "- `resultados/tabelas/`: descritivas, mapa de evidências, resumos físico-químicos e de agrupamentos, "
        "prontidão para meta-análise, auditoria de faltantes, associações exploratórias (XLSX e CSV)\n"
        "- `resultados/figuras/`: figuras em alta resolução (PNG/TIFF) e painel composto\n"
        "- `resultados/qualidade_JBI/`: avaliação da qualidade metodológica (JBI adaptado)\n"
        "- `revisao_manual/`: modelos de revisão manual\n"
        "- `estrategias_busca/`: estratégias de busca\n"
        "- `registros_analise/`: logs de execução\n"
        "- `sinteses/`: sínteses discursivas por artigo (PDF, RIS, MD) e figuras extraídas\n"
        "- `extracao/`: planilha de extração revisada; `correcoes/`: decisões de revisão manual\n"
        "- `codigo/`: código Python (pacote article_reader) e esquema\n"
        "- `manifesto_execucao.json`: versões de software, parâmetros e SHA-256 de entradas e saídas\n\n"
        "## Como reproduzir\n"
        "```bash\npip install -r requirements.txt\n"
        "python -m article_reader analisar executar --extracao dados/brutos/extracao_bruta.xlsx "
        "--esquema dados/brutos/esquema_utilizado.json --correcoes correcoes/correcoes.xlsx "
        "--saida reproducao/\n```\n"
        "Compare os hashes de `reproducao/manifesto_execucao.json` com os deste pacote "
        "(figuras podem diferir em metadados binários entre versões do matplotlib).\n\n"
        f"Ambiente original: Python {v['python']} — {v['plataforma']}.\n",
        encoding="utf-8")
    linhas = [f"{sha256(p)}  {p.relative_to(dest).as_posix()}" for p in sorted(dest.rglob("*")) if p.is_file()]
    (dest / "CHECKSUMS.sha256").write_text("\n".join(linhas) + "\n", encoding="utf-8")
    if compactar:
        zipado = dest.with_suffix(".zip")
        with zipfile.ZipFile(zipado, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(dest.rglob("*")):
                if p.is_file():
                    z.write(p, p.relative_to(dest.parent))
        return zipado
    return dest


# Comand
def _pdfs(args) -> list[Path]:
    arquivos = [Path(p) for p in (args.pdf or [])]
    if args.pasta:
        arquivos += sorted(p for p in Path(args.pasta).rglob("*") if p.suffix.lower() == ".pdf")
    if not arquivos:
        raise SystemExit("Informe --pasta ou --pdf.")
    return arquivos

def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m article_reader analisar",
                                description="Análises reprodutíveis da revisão sistemática.")
    sub = p.add_subparsers(dest="comando", required=True)

    def entrada_pdfs(sp):
        sp.add_argument("--pdf", nargs="*", help="Caminhos de PDFs")
        sp.add_argument("--pasta", help="Pasta com PDFs (inclui subpastas)")

    s = sub.add_parser("esquema", help="Gera esquema.json editável")
    s.add_argument("--saida", default="esquema.json")

    s = sub.add_parser("modelo-extracao", help="Planilha de extração bruta em branco")
    s.add_argument("--esquema")
    s.add_argument("--saida", default="extracao_bruta.xlsx")

    s = sub.add_parser("qualidade", help="Pré-avaliação JBI adaptada")
    entrada_pdfs(s)
    s.add_argument("--esquema")
    s.add_argument("--checklist", choices=sorted(CHECKLISTS_JBI))
    s.add_argument("--saida", default="avaliacao_qualidade_modelo.xlsx")

    s = sub.add_parser("executar", help="Harmonização, tabelas, figuras, prontidão para MA e manifesto")
    s.add_argument("--extracao", required=True)
    s.add_argument("--esquema")
    s.add_argument("--correcoes")
    s.add_argument("--qualidade")
    s.add_argument("--repositorio", default="[inserir repositório/DOI]")
    s.add_argument("--saida", default="resultados_analises")

    s = sub.add_parser("repositorio", help="Pacote para depósito (.zip + SHA-256)")
    s.add_argument("--resultados", required=True)
    s.add_argument("--estrategias")
    s.add_argument("--extra", nargs="*", default=[])
    s.add_argument("--saida", default="pacote_repositorio")

    args = p.parse_args(argv)

    if args.comando == "esquema":
        print(f"Esquema salvo em {salvar_esquema_modelo(args.saida)}")
    elif args.comando == "modelo-extracao":
        print(f"Planilha salva em {criar_modelo_extracao(args.saida, carregar_esquema(args.esquema))}")
    elif args.comando == "qualidade":
        esquema = carregar_esquema(args.esquema)
        avaliacao = avaliar_qualidade_pdfs(_pdfs(args), args.checklist or esquema["qualidade"]["checklist_padrao"])
        print(f"Planilha salva em {criar_modelo_qualidade(avaliacao, args.saida, esquema)}")
    elif args.comando == "executar":
        r = executar_analises(args.extracao, args.saida, esquema=carregar_esquema(args.esquema),
                              caminho_correcoes=args.correcoes, caminho_qualidade=args.qualidade,
                              repositorio=args.repositorio)
        print("\n" + r["justificativa"] + f"\n\nPendências de revisão manual: {r['pendencias']} | {r['pasta']}")
    elif args.comando == "repositorio":
        codigo = sorted(Path(__file__).resolve().parent.glob("*.py"))
        destino = montar_repositorio(args.resultados, args.saida, codigo=codigo,
                                     estrategias_busca=args.estrategias,
                                     extras=[Path(e) for e in args.extra])
        print(f"Pacote: {destino}")
    return 0