"""Seleção dos trechos de cada artigo."""

from __future__ import annotations

import math
import re
from collections import Counter

from .config import Config
from .models import Artigo, Frase
from .sections import FraseBruta

_I = re.IGNORECASE

PISTAS_RESULTADO = re.compile(
    r"\b(show(?:ed|n|s)?|reveal(?:ed|s)?|indicat(?:ed|es)|increas(?:ed|es|ing)?|decreas(?:ed|es|ing)?|"
    r"reduc(?:ed|es|tion)|enhanc(?:ed|es|ement)|improv(?:ed|es|ement)|higher|lower|greater|highest|lowest|"
    r"significant(?:ly)?|identified|detected|quantified|correlat(?:ed|ion|ions)|associated|contribut(?:ed|ion|ions)|"
    r"resulted in|led to|differ(?:ed|ences?)|distinguish(?:ed)?|discriminat(?:ed|ion)|classif(?:ied|ication)|"
    r"accuracy|predict(?:ed|ion)|found|observed|exhibit(?:ed|s)?|characteri[sz]ed|dominat(?:ed|es)|"
    r"most abundant|predominant|key|main|major|"
    r"mostr(?:ou|aram|ó|aron)|aument(?:ou|aram|ó)|diminu(?:iu|íram|yó)|reduz(?:iu|iram)|signific(?:ativ|ativa)|"
    r"observ(?:ou|ado|ó)|identific(?:ou|ados|aron)|apresent(?:ou|aram|ó))\b",
    _I,
)
PISTAS_INTERPRETACAO = re.compile(
    r"\b(may|might|could|suggest(?:s|ed|ing)?|likely|possibl[ey]|probabl[ey]|attribut(?:ed|able)|"
    r"explain(?:ed|s)?|explanation|due to|because|owing to|indicating|implies|implied|hypothes|"
    r"consistent with|in agreement|in line with|contrary to|in contrast|whereas|mechanism|"
    r"pode(?:m)?|sugere|provavelmente|devido|explica|puede|sugiere|debido)\b",
    _I,
)
PISTAS_CONCLUSAO = re.compile(
    r"\b(in conclusion|in summary|overall|taken together|to conclude|in short|"
    r"(?:these|our|the present) (?:results|findings|data) (?:demonstrate|show|indicate|suggest|highlight|provide|confirm)|"
    r"this (?:study|work|research) (?:demonstrates|demonstrated|shows|showed|provides|highlights|confirms|revealed|reveals)|"
    r"em conclusão|conclui-se|en conclusión)\b",
    _I,
)
PISTAS_LIMITACAO = re.compile(
    r"\b(limitation|limited (?:by|to|number|sample|data)|further (?:stud|research|investigation|work|analys|validation|exploration)|"
    r"future (?:stud|research|work|investigation)|should be (?:investigated|explored|further|evaluated|validated|confirmed|considered)|"
    r"remains? (?:unclear|unknown|to be)|need(?:s|ed)? to be (?:further|investigated|confirmed|validated|explored|clarified)|"
    r"warrant|not (?:been )?(?:assessed|evaluated|investigated|considered|addressed)|small sample|"
    r"single (?:origin|harvest|season|batch|cultivar|variety)|is needed|are needed|"
    r"limita[çc][ãa]o|estudos futuros|investigaciones futuras)",
    _I,
)
PISTAS_METODO = re.compile(
    r"\b(were (?:performed|carried out|prepared|purchased|obtained from|conducted|used|analy[sz]ed using|ground|stored|placed|"
    r"collected|harvested|weighed|filtered|centrifuged|injected|incubated|diluted|dissolved|mixed)|"
    r"was (?:performed|carried out|prepared|used|conducted|set|applied|calculated|determined using|measured using|equipped)|"
    r"according to|as described|following the (?:method|procedure)|equipped with|calibrat|injector|carrier gas|"
    r"flow rate|split ratio|oven temperature|column \(|ramped|held for|were recorded|was recorded|in triplicate|"
    r"the aim of this|this study aimed|the objective of|aimed to|we aimed|were evaluated|was evaluated|were investigated|was investigated|"
    r"this (?:study|work|research|paper) (?:compared|investigated|evaluated|examined|explored|analy[sz]ed|aimed|assessed|characteri[sz]ed)|"
    r"we (?:compared|investigated|evaluated|examined|explored|analy[sz]ed|aimed|assessed|used|applied)|"
    r"deconvolution|threshold of|S/N|signal-to-noise|retention (?:time|index|indices)|calibration curve|limit of (?:detection|quantification)|"
    r"tentatively (?:assigned|identified)|were (?:then )?subjected to|was (?:then )?subjected to|in this section)\b",
    _I,
)
RE_DESCRITIVA = re.compile(
    r"\b(?:is|are|were|was) (?:shown|presented|summari[sz]ed|listed|displayed|illustrated|given|depicted) in\b|"
    r"\b(?:Table|Figure|Fig\.) \d+[A-Za-z]? (?:shows|presents|summari[sz]es|lists|displays|illustrates|depicts)",
)
RE_QUANTITATIVO = re.compile(
    r"\d+(?:[.,]\d+)?\s?%|\bp\s*[<>=≤]\s*0?[.,]\d+|\bR2\b|R²|\br\s*=\s*-?0?[.,]\d|"
    r"\d+(?:[.,]\d+)?\s?(?:µg|μg|mg|ng|g|kg|mL|L|°C|min|h|ppm|ppb)\b|\bfold\b|\b\d+(?:[.,]\d+)? times\b",
    _I,
)
RE_PROPRIO = re.compile(
    r"\b(this study|the present study|the current study|this work|our (?:results|findings|study|data|work)|"
    r"we (?:found|observed|identified|showed|demonstrated|detected)|in this research|este estudo|presente estudo|"
    r"nossos resultados|este trabajo)\b",
    _I,
)
RE_CITA_EXTERNA = re.compile(
    r"\[\s*\d+(?:\s*[,–\-−]\s*\d+)*\s*\]|\[cit\]|\bet al\.|"
    r"\(\s*[A-Z][\w'’\-]+(?:\s+(?:and|&|e|y)\s+[A-Z][\w'’\-]+)?(?:\s+et al\.?)?,?\s+(?:19|20)\d{2}[a-z]?[^()]{0,40}\)"
)
RE_RUIDO = re.compile(
    r"^(?:>|\d+\s+[A-Z]|values are|data are|means? (?:with|±)|note:|abbreviations?:|\*|†|‡|a,b|different letters|"
    r"copyright|©|received|accepted|published|available online|e-mail|doi:|https?://)",
    _I,
)
RE_AUMENTO = re.compile(r"\b(increas\w*|higher|enhanc\w*|greater|more abundant|elevated|ros[ea]|improv\w*|rais\w*|aument\w*|maior\w*)\b", _I)
RE_REDUCAO = re.compile(r"\b(decreas\w*|lower|reduc\w*|declin\w*|diminish\w*|less abundant|dropp\w*|loss|lost|diminu\w*|menor\w*)\b", _I)


STOP = set(
    """a an the and or of to in on for with by from as at is are was were be been being this that these those it its
    their there which who whom whose than then also into between among during after before such both each other more most
    less least very can could may might will would should our we they he she them his her not no nor only same so too
    using used use based study studies results result data showed show shown found well however therefore thus while""".split()
)


def palavras_conteudo(texto: str) -> set[str]:
    return {_raiz(p) for p in re.findall(r"[a-zA-Zà-ÿ][a-zA-Zà-ÿ0-9\-]{3,}", texto.lower()) if p not in STOP}

def _raiz(palavra: str) -> str:
    for sufixo in ("ations", "ation", "ings", "ing", "ies", "ed", "es", "s"):
        if palavra.endswith(sufixo) and len(palavra) - len(sufixo) >= 4:
            return palavra[: -len(sufixo)]
    return palavra

def similaridade(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / math.sqrt(len(a) * len(b))

def sentido(texto: str) -> str:
    sobe, desce = bool(RE_AUMENTO.search(texto)), bool(RE_REDUCAO.search(texto))
    if sobe and not desce:
        return "aumento"
    if desce and not sobe:
        return "reducao"
    return ""


_CURTAS_COMUNS = {"a", "an", "as", "at", "be", "by", "do", "if", "in", "is", "it", "no", "of", "on", "or", "so", "to", "up", "we",
                  "vs", "ph", "mg", "ml", "ng", "nm", "mm", "cm", "kg", "μg", "µg", "min", "h", "g", "l", "s", "e", "y", "o", "de", "la",
                  "el", "en", "se", "da", "do", "em", "os", "un", "al", "lo", "ii", "iv", "vi", "cv", "var", "sp", "ca", "et", "i", "n", "p"}
_RE_ABREV_MEIO = re.compile(r"\b(?:al|vs|approx|ca|var|cv|spp?|fig|figs|eq|ref|resp|min|max|no)\. [a-z]", re.IGNORECASE)


def parece_corrompida(texto: str, df: Counter | None = None, tf_doc: Counter | None = None) -> bool:
    """Detecta texto embaralhado (colunas misturadas, OCR ruim, codificação quebrada)."""
    if re.search(r"[\ufffd\u25a1\ue000-\uf8ff]|Â", texto):
        return True
    if sum(1 for c in texto if "\u1100" <= c <= "\u9fff" or "\uac00" <= c <= "\ud7af") > 3:
        return True  # trechos em coreano/chinês/japonês
    if texto.count("(") != texto.count(")") or texto.count("[") != texto.count("]"):
        return True
    if re.search(r"\b[a-z]{3,}[A-Z][a-z]{2,}", texto):           # "precurAuthor"
        return True
    if re.search(r"\b[a-z]{3,}\. [a-z]{3,}\b", texto) and not _RE_ABREV_MEIO.search(texto):  # "study. quality"
        return True
    if re.search(r"[!|]|—-|_ ", texto):
        return True
    tokens = re.findall(r"[A-Za-zÀ-ÿ]+", texto)
    estranhos = [t for t in tokens if len(t) == 2 and t.islower() and t not in _CURTAS_COMUNS]
    if len(estranhos) >= 2:
        return True
    if df is not None and tokens:
        longas = [t for t in tokens if len(t) >= 4 and not re.search(r"[A-Z].*[A-Z]", t)]
        # desconhecida = só existe neste artigo E aparece uma única vez nele (fragmento de OCR/colunas)
        desconhecidas = [t for t in longas if df.get(t.lower(), 0) <= 1 and (tf_doc is None or tf_doc[t.lower()] <= 1)]
        if longas and len(desconhecidas) / len(longas) > 0.15:
            return True
    return False

def frase_valida(f: FraseBruta, cfg: Config, df: Counter | None = None, tf_doc: Counter | None = None) -> bool:
    texto = f.texto
    if parece_corrompida(texto, df, tf_doc):
        return False
    n = len(texto.split())
    if n < cfg.min_palavras or n > cfg.max_palavras:
        return False
    if f.cita_externa or RE_CITA_EXTERNA.search(texto):
        return False
    if RE_RUIDO.search(texto) or "|" in texto or "http" in texto:
        return False
    if not re.search(r"[.!?]['\"”’)]*$", texto):
        return False  # frase truncada (quebra de coluna/tabela)
    digitos = sum(c.isdigit() for c in texto)
    if digitos / max(len(texto), 1) > 0.18 or len(re.findall(r"\d+(?:[.,]\d+)?", texto)) > 10:
        return False  # linha de tabela
    if re.search(r"\b(Fig(?:ure)?\.?|Table)\s*S\d", texto):
        return False  # material suplementar, inacessível ao leitor
    letras = sum(c.isalpha() for c in texto)
    return letras / max(len(texto), 1) > 0.55

def _pontuar(f: FraseBruta, resumo: set[str]) -> dict[str, float]:
    t = f.texto
    sim = similaridade(palavras_conteudo(t), resumo)
    n_res = min(len(PISTAS_RESULTADO.findall(t)), 3)
    n_int = min(len(PISTAS_INTERPRETACAO.findall(t)), 3)
    quant = 1.0 if RE_QUANTITATIVO.search(t) else 0.0
    proprio = 1.5 if RE_PROPRIO.search(t) else 0.0
    metodo = 3.0 if PISTAS_METODO.search(t) else 0.0
    referencia_tabela = 0.8 if re.match(r"^(As (?:shown|can be seen|presented|illustrated|depicted)|(?:Table|Figure|Fig\.) \d)", t) else 0.0
    if RE_DESCRITIVA.search(t):
        referencia_tabela += 2.0
    return {
        "resultado": n_res + quant + proprio + 3.0 * sim - metodo - referencia_tabela - 0.3 * n_int,
        "discussao": n_int + 0.8 * min(n_res, 2) + 0.5 * quant + proprio + 2.5 * sim - metodo,
        "conclusao": (1.5 if PISTAS_CONCLUSAO.search(t) else 0.0) + 0.6 * n_res + proprio + 3.0 * sim - metodo
        - (1.0 if re.match(r"^(For example|For instance|E\.g\.)", t) else 0.0) - referencia_tabela,
    }

def _escolher(candidatas: list[tuple[float, FraseBruta]], k: int, usadas: set[int]) -> list[tuple[float, FraseBruta]]:
    """Melhores k frases, evitando repetidas e quase-duplicadas (diversidade)."""
    escolhidas: list[tuple[float, FraseBruta]] = []
    for pontos, f in sorted(candidatas, key=lambda x: -x[0]):
        if len(escolhidas) >= k:
            break
        if f.ordem in usadas or pontos <= 0:
            continue
        palavras = palavras_conteudo(f.texto)
        if any(similaridade(palavras, palavras_conteudo(e.texto)) > 0.6 for _, e in escolhidas):
            continue
        escolhidas.append((pontos, f))
        usadas.add(f.ordem)
    return escolhidas

def _para_frase(pontos: float, f: FraseBruta) -> Frase:
    return Frase(f.texto, f.pagina, f.categoria, f.secao, f.ordem, round(pontos, 3), sentido(f.texto))

def selecionar_trechos(artigo: Artigo, frases: list[FraseBruta], cfg: Config, df: Counter | None = None) -> None:
    resumo = palavras_conteudo(artigo.metadados.resumo + " " + artigo.metadados.titulo)
    cats = set(artigo.categorias_encontradas)
    tem_resultados = bool(cats & {"resultados", "resultados_discussao"})
    tem_discussao = bool(cats & {"discussao", "resultados_discussao"})
    tem_conclusao = "conclusao" in cats

    if tem_resultados:
        cat_res = {"resultados", "resultados_discussao"}
    elif cats & {"desenvolvimento", "discussao"}:
        cat_res = {"desenvolvimento", "discussao"}
        artigo.alertas.append("Seção de resultados não identificada; trechos buscados no desenvolvimento do texto.")
    else:
        cat_res = {"resumo", "desenvolvimento", "pre"} if not cats - {"pre", "referencias", "fim"} else {"desenvolvimento", "resumo"}
        artigo.alertas.append("Estrutura de seções não identificada; trechos buscados em todo o texto.")
    cat_disc = {"discussao", "resultados_discussao"} if tem_discussao else cat_res
    if tem_conclusao:
        cat_conc = {"conclusao"}
    else:
        cat_conc = cat_disc
        artigo.alertas.append("Seção de conclusão não identificada; conclusões buscadas no fim da discussão.")

    tf_doc = Counter(p.lower() for f in frases for p in re.findall(r"[A-Za-zÀ-ÿ]+", f.texto))
    validas = [f for f in frases if f.categoria not in ("referencias", "fim", "metodos", "introducao") and frase_valida(f, cfg, df, tf_doc)]
    if not validas:
        artigo.alertas.append("Nenhuma frase aproveitável encontrada no texto convertido.")
        return
    pontos = {f.ordem: _pontuar(f, resumo) for f in validas}
    ultima = max(f.ordem for f in validas)

    def entre(cats_alvo):
        return [f for f in validas if f.categoria in cats_alvo]

    usadas: set[int] = set()
    artigo.limitacoes = []

    conc_cand = entre(cat_conc)
    if not tem_conclusao:
        conc_cand = [f for f in conc_cand if f.ordem >= ultima * 0.75 or PISTAS_CONCLUSAO.search(f.texto)]
    conc = [(pontos[f.ordem]["conclusao"], f) for f in conc_cand]
    artigo.conclusoes = [_para_frase(p, f) for p, f in _escolher(conc, cfg.conclusoes, usadas)]

    res = [(pontos[f.ordem]["resultado"], f) for f in entre(cat_res) if PISTAS_RESULTADO.search(f.texto)]
    artigo.resultados = [_para_frase(p, f) for p, f in _escolher(res, cfg.resultados, usadas)]

    disc = [(pontos[f.ordem]["discussao"], f) for f in entre(cat_disc) if PISTAS_INTERPRETACAO.search(f.texto)]
    artigo.discussoes = [_para_frase(p, f) for p, f in _escolher(disc, cfg.discussoes, usadas)]

    todas = [(pontos[f.ordem]["resultado"], f) for f in entre(cat_res | cat_disc | cat_conc) if PISTAS_RESULTADO.search(f.texto)]
    artigo.candidatas = [_para_frase(p, f) for p, f in sorted(todas, key=lambda x: -x[0])[:25] if p > 0]

    if not artigo.resultados:
        artigo.alertas.append("Nenhum resultado selecionado automaticamente.")
    if not artigo.conclusoes:
        artigo.alertas.append("Nenhuma conclusão selecionada automaticamente.")


TECNICAS: dict[str, list[tuple[str, str]]] = {
    "analitica": [
        ("GC×GC", r"GC\s?[×x]\s?GC|(?i:comprehensive two-dimensional gas chromatography)"),
        ("GC–IMS", r"GC[-–\s]?IMS|(?i:ion mobility spectrometry)"),
        ("GC–O (olfatometria)", r"GC[-–\s]?O\b|GC[-–]O[-–]|(?i:olfactometr)"),
        ("GC–MS", r"GC[-–\s]?(?:Q[-–\s]?)?(?:TOF[-–\s]?)?MS|(?i:gas chromatography[-–\s](?:coupled (?:to|with) )?(?:\w+[-–\s])*mass spectrometry)"),
        ("LC–MS", r"\b(?:U?H?P?LC|UPLC|UHPLC)[-–\s]?(?:ESI[-–\s]?(?:\(±\))?[-–\s]?)?(?:Q[-–\s]?)?(?:TOF|Orbitrap|QqQ|LTQ)?[-–\s]?MS|(?i:liquid chromatography[-–\s](?:\w+[-–\s])*mass spectrometry)|Orbitrap"),
        ("HPLC", r"\bHPLC\b(?![-–\s]?MS)|(?i:high[- ]performance liquid chromatography)(?! ?[-–]? ?(?i:mass))"),
        ("RMN", r"\bNMR\b|(?i:nuclear magnetic resonance)"),
        ("espectroscopia (NIR/FTIR/Raman)", r"\bNIRS?\b|\bFT-?IR\b|(?i:near[- ]infrared|raman spectroscopy)"),
        ("PTR/SIFT-MS", r"PTR[-–]?(?:TOF[-–]?)?MS|SIFT[-–]?MS|(?i:proton[- ]transfer reaction)"),
        ("nariz eletrônico", r"(?i:electronic nose|\be-nose\b)"),
        ("língua eletrônica", r"(?i:electronic tongue|\be-tongue\b)"),
        ("sequenciamento microbiano", r"\b16S\b|\bITS[12]?\b(?! (?i:is|was))|(?i:metagenom|amplicon sequencing|high-throughput sequencing|metagenetic|illumina)"),
    ],
    "extracao": [
        ("HS-SPME", r"HS[-–]?SPME|\bSPME\b|(?i:solid[- ]phase microextraction)"),
        ("SAFE", r"\bSAFE\b|(?i:solvent[- ]assisted flavou?r evaporation)"),
        ("headspace estático/dinâmico", r"\bSHS\b|\bSBSE\b|HiSorb|(?i:static headspace|dynamic headspace|purge and trap|stir bar sorptive)"),
    ],
    "sensorial": [
        ("protocolo SCA (prova de xícara)", r"\bSCAA?\b|(?i:cupping|q[- ]graders?)"),
        ("análise descritiva quantitativa", r"\bQDA\b|(?i:quantitative descriptive|descriptive (?:sensory )?analysis|trained panel)"),
        ("CATA", r"\bCATA\b|(?i:check[- ]all[- ]that[- ]apply)"),
        ("testes com consumidores", r"(?i:consumer (?:test|panel|acceptance|preference|study)|hedonic|acceptance test|purchase intent|untrained (?:panel|assessors|consumers))"),
        ("testes discriminativos", r"(?i:triangle test|triangular test|duo[- ]trio)"),
        ("TDS (dominância temporal)", r"(?i:temporal dominance of sensations|temporal dominance)"),
    ],
    "estatistica": [
        ("PCA", r"\bPCA\b|(?i:principal component analysis)"),
        ("PLS-DA/OPLS-DA", r"\b(?:O?PLS[-–]?DA|OPLS|PLSR?)\b|(?i:partial least squares)"),
        ("análise de agrupamento", r"\bHCA\b|(?i:hierarchical cluster|heat ?map|cluster analysis)"),
        ("aprendizado de máquina", r"\bSVM\b|\bk-?NN\b|XGBoost|(?i:machine learning|random forest|support vector|neural network|deep learning)"),
        ("ANOVA", r"\bANOVA\b|(?i:analysis of variance|tukey)"),
        ("redes de correlação", r"\bWGCNA\b|(?i:correlation network|pearson(?:'s)? correlation|spearman)"),
        ("valor de atividade odorífera (OAV)", r"\br?OAVs?\b|(?i:odou?r activity value)"),
    ],
}
_TECNICAS_RE = {grupo: [(rot, re.compile(p)) for rot, p in itens] for grupo, itens in TECNICAS.items()}


def detectar_tecnicas(texto: str) -> list[str]:
    encontradas = []
    for itens in _TECNICAS_RE.values():
        for rotulo, padrao in itens:
            if padrao.search(texto):
                encontradas.append(rotulo)
    return encontradas

def grupo_tecnica(rotulo: str) -> str:
    for grupo, itens in TECNICAS.items():
        if any(r == rotulo for r, _ in itens):
            return grupo
    return ""

def contar_tecnicas(artigos: list[Artigo], grupo: str) -> list[tuple[str, int]]:
    contagem = Counter(t for a in artigos for t in set(a.tecnicas) if grupo_tecnica(t) == grupo)
    return contagem.most_common()