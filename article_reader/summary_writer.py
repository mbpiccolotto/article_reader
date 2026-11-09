"""Redação do resumo integralizado."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from itertools import cycle

from .passage_selection import contar_tecnicas
from .citations import citacao, citacao_narrativa, plural
from .config import Config
from .pluralization import dos, pl, vb


# Blocos
"""Blocos do documento e pequenos auxiliares de formatação."""

ESTUDO = "estudo"
from .models import Artigo, Frase
from .thematic_axes import Eixo, Tema

IT_INI, IT_FIM = "\x01", "\x02"

@dataclass
class Bloco:
    tipo: str
    texto: str

@dataclass
class Documento:
    blocos: list[Bloco] = field(default_factory=list)
    citados: set[str] = field(default_factory=set)
    trechos_usados: int = 0

def italico(texto: str) -> str:
    return f"{IT_INI}{texto}{IT_FIM}"

def lista(itens: list[str], conj: str = "e") -> str:
    itens = [i for i in itens if i]
    if not itens:
        return ""
    return itens[0] if len(itens) == 1 else ", ".join(itens[:-1]) + f" {conj} " + itens[-1]

def _rotulo_tema(tema: Tema) -> str:
    return tema.rotulo if tema.traduzido else italico(tema.rotulo)

def _pct(n: int, total: int) -> str:
    return f"{round(100 * n / total)}%" if total else "0%"


# Vocabulário
VERBOS_RESULTADO = [("observa", "observam"), ("relata", "relatam"), ("constata", "constatam"), ("verifica", "verificam"),
                    ("demonstra", "demonstram"), ("registra", "registram"), ("evidencia", "evidenciam"), ("identifica", "identificam")]
VERBOS_DISCUSSAO = [("argumenta", "argumentam"), ("sugere", "sugerem"), ("pondera", "ponderam"), ("propõe", "propõem"),
                    ("considera", "consideram"), ("explica", "explicam")]
VERBOS_CONCLUSAO = [("conclui", "concluem"), ("afirma", "afirmam"), ("destaca", "destacam"), ("sintetiza", "sintetizam")]
CONECTIVOS_CONVERGENCIA = ["Na mesma linha, ", "Em outro estudo, ", "Igualmente, ", "Também nesse tema, ", "Em perspectiva próxima, "]
CONECTIVOS_COMPLEMENTO = ["Complementarmente, ", "Além disso, ", "Sob outra perspectiva, ", "Ampliando esse quadro, ", "Em outro contexto experimental, "]
CONECTIVOS_DISCUSSAO = ["Ao interpretar seus resultados, ", "", "Nessa perspectiva, ", "Quanto aos mecanismos envolvidos, ", ""]
CONECTIVOS_CONCLUSAO = ["", "Em termos conclusivos, ", "Ao final de seu estudo, ", "Na mesma direção, ", "Como síntese de seus achados, "]


# Redator
"""Acumula frases, citações e trechos em parágrafos e blocos."""

class Redator:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.doc = Documento()
        self._paragrafo: list[str] = []
        self._verbos = {"resultado": cycle(VERBOS_RESULTADO), "discussao": cycle(VERBOS_DISCUSSAO), "conclusao": cycle(VERBOS_CONCLUSAO)}
        self._contador = 0
        self.usadas: set[tuple[str, int]] = set()

    def titulo(self, texto: str, nivel: int = 1) -> None:
        self.fechar()
        self.doc.blocos.append(Bloco(f"titulo{nivel}", texto))

    def frase(self, texto: str) -> None:
        self._paragrafo.append(texto.strip())

    def fechar(self) -> None:
        if self._paragrafo:
            self.doc.blocos.append(Bloco("paragrafo", " ".join(self._paragrafo)))
            self._paragrafo = []

    def citar_grupo(self, artigos: list[Artigo]) -> str:
        self.doc.citados.update(a.chave for a in artigos)
        return citacao(artigos)

    def citar_trecho(self, artigo: Artigo, frase: Frase, tipo: str, conector: str = "") -> None:
        self.doc.citados.add(artigo.chave)
        self.usadas.add((artigo.chave, frase.ordem))
        self.doc.trechos_usados += 1
        trecho = frase.texto.strip().rstrip(".").rstrip()
        sg, pl = next(self._verbos[tipo])
        verbo = pl if plural(artigo) else sg
        self._contador += 1
        if len(trecho.split()) > self.cfg.citacao:
            abertura = f"{conector}{citacao_narrativa(artigo, frase.pagina)} {verbo}:"
            self.frase(_maiuscula(abertura))
            self.fechar()
            self.doc.blocos.append(Bloco("citacao_longa", trecho + "."))
            return
        if self._contador % 3 == 0 and conector and tipo == "resultado":
            impessoal = ("registra-se que", "verifica-se que", "observa-se que")[(self._contador // 3) % 3]
            self.frase(_maiuscula(f"{conector}{impessoal} “{trecho}” {citacao(artigo, frase.pagina)}."))
        else:
            self.frase(_maiuscula(f"{conector}{citacao_narrativa(artigo, frase.pagina)} {verbo} que “{trecho}”."))

    def ja_usada(self, artigo: Artigo, frase: Frase) -> bool:
        return (artigo.chave, frase.ordem) in self.usadas

def _maiuscula(texto: str) -> str:
    for i, c in enumerate(texto):
        if c.isalpha():
            return texto[:i] + c.upper() + texto[i + 1:]
    return texto


# Seções
"""Escreve a introdução, uma seção por eixo e as considerações finais."""

def redigir(artigos: list[Artigo], eixos: list[Eixo], cfg: Config) -> Documento:
    r = Redator(cfg)
    _introducao(r, artigos, eixos)
    for n, eixo in enumerate(eixos, start=2):
        _eixo(r, eixo, n)
    _consideracoes(r, artigos, eixos, len(eixos) + 1)
    r.fechar()
    return r.doc

def _introducao(r: Redator, artigos: list[Artigo], eixos: list[Eixo]) -> None:
    total = len(artigos)
    anos = sorted(int(a.metadados.ano) for a in artigos if a.metadados.ano.isdigit())
    periodicos = Counter(a.metadados.periodico for a in artigos if a.metadados.periodico)
    r.titulo("1 Introdução")
    texto = f"Esta síntese integra os resultados, as discussões e as conclusões de {pl(total, 'estudo')}"
    if anos:
        texto += (f" {vb(total, 'publicado', 'publicados')} entre {anos[0]} e {anos[-1]}" if anos[0] != anos[-1]
                  else f" {vb(total, 'publicado', 'publicados')} em {anos[0]}")
    if periodicos:
        texto += f", {vb(total, 'veiculado', 'veiculados')} em {pl(len(periodicos), 'periódico científico', 'periódicos científicos')}"
    r.frase(texto + ".")
    if periodicos:
        top = [(p, n) for p, n in periodicos.most_common(4) if n > 1]
        if top:
            r.frase(f"Os periódicos mais frequentes foram {lista([f'{italico(p)} ({pl(n, ESTUDO)})' for p, n in top])}.")
    if len(anos) >= 4:
        mediana = anos[len(anos) // 2]
        recentes = sum(1 for a in anos if a >= mediana)
        r.frase(f"A produção concentra-se nos anos mais recentes: {pl(recentes, 'estudo')} ({_pct(recentes, len(anos))}) {vb(recentes, 'foi publicado', 'foram publicados')} a partir de {mediana}.")
    r.fechar()

    analiticas = contar_tecnicas(artigos, "analitica")[:4]
    rotulos_sensoriais = dict(contar_tecnicas(artigos, "sensorial"))
    sensoriais = [a for a in artigos if any(t in rotulos_sensoriais for t in a.tecnicas)]
    estat = contar_tecnicas(artigos, "estatistica")[:3]
    if analiticas:
        r.frase("Do ponto de vista metodológico, as abordagens analíticas mais empregadas foram "
                f"{lista([f'{t} ({pl(n, ESTUDO)})' for t, n in analiticas])}.")
    if sensoriais:
        r.frase("A avaliação sensorial está presente no estudo analisado." if total == 1 else
                f"A avaliação sensorial está presente em {len(sensoriais)} {dos(total)} ({_pct(len(sensoriais), total)}).")
    if estat:
        r.frase(f"No tratamento dos dados, predominam {lista([f'{t} ({n})' for t, n in estat])}.")
    r.fechar()

    if len(eixos) > 1:
        descricao = lista([f"“{e.titulo}” ({pl(len(e.artigos), 'estudo')})" for e in eixos])
        r.frase(f"Para integrar os achados, os estudos foram organizados em {len(eixos)} eixos temáticos, definidos pela similaridade "
                f"de conteúdo entre títulos, resumos, palavras-chave e conclusões: {descricao}.")
    r.frase("Em cada eixo, apresentam-se o panorama dos estudos, os resultados, organizados pelos temas que aparecem em mais de "
            "um trabalho, e as interpretações e conclusões dos autores. Os trechos dos estudos são reproduzidos como citações "
            "diretas, no idioma original e com indicação de página, de modo a preservar a fidelidade aos achados relatados.")
    r.fechar()

def _eixo(r: Redator, eixo: Eixo, n: int) -> None:
    artigos = eixo.artigos
    r.titulo(f"{n} {eixo.titulo}")

    r.titulo(f"{n}.1 Panorama dos estudos", 2)
    anos = sorted(int(a.metadados.ano) for a in artigos if a.metadados.ano.isdigit())
    publ = vb(len(artigos), "publicado", "publicados")
    periodo = f", {publ} entre {anos[0]} e {anos[-1]}" if anos and anos[0] != anos[-1] else (f", {publ} em {anos[0]}" if anos else "")
    r.frase(f"Este eixo reúne {pl(len(artigos), 'estudo')}{periodo} {r.citar_grupo(artigos)}.")
    if eixo.temas:
        r.frase(f"Os achados que atravessam mais de um trabalho referem-se a {lista([_rotulo_tema(t) for t in eixo.temas])}.")
    analiticas = contar_tecnicas(artigos, "analitica")[:3]
    extracao = contar_tecnicas(artigos, "extracao")[:2]
    sensoriais = contar_tecnicas(artigos, "sensorial")[:3]
    estat = contar_tecnicas(artigos, "estatistica")[:3]
    if analiticas:
        r.frase(f"Quanto às técnicas analíticas, destacam-se {lista([f'{t} ({k})' for t, k in analiticas])}"
                + (f", com preparo de amostra predominantemente por {lista([t for t, _ in extracao], 'ou')}" if extracao else "") + ".")
    if sensoriais:
        com_sensorial = sum(1 for a in artigos if any(t in dict(sensoriais) for t in a.tecnicas))
        r.frase(("A dimensão sensorial é avaliada no estudo, " if len(artigos) == 1 else
                 f"A dimensão sensorial é avaliada em {com_sensorial} {dos(len(artigos))}, ") + "principalmente por meio de "
                f"{lista([t for t, _ in sensoriais])}.")
    if estat:
        r.frase(f"Na análise dos dados, recorrem com maior frequência a {lista([t for t, _ in estat])}.")
    r.fechar()

    r.titulo(f"{n}.2 Resultados", 2)
    for i, tema in enumerate(eixo.temas):
        _tema(r, tema, i)
    restantes = []
    for a in artigos:
        livres = [f for f in a.resultados if not r.ja_usada(a, f)]
        if livres and not any(art.chave == a.chave for t in eixo.temas for art, _ in t.trechos):
            restantes.append((a, livres[0]))
    if restantes:
        r.frase("Além dos pontos em comum, os demais estudos do eixo trazem contribuições específicas." if eixo.temas
                else "Os principais resultados dos estudos deste eixo são apresentados a seguir.")
        conectivos = cycle(CONECTIVOS_COMPLEMENTO)
        for j, (a, f) in enumerate(restantes):
            r.citar_trecho(a, f, "resultado", "" if j == 0 else next(conectivos))
            if (j + 1) % 4 == 0:
                r.fechar()
        r.fechar()
    adicionais = []
    for a in artigos:
        livres = [f for f in a.resultados if not r.ja_usada(a, f)]
        if livres:
            adicionais.append((a, livres[0]))
    if adicionais:
        r.frase("Outros resultados relevantes complementam esse quadro.")
        conectivos = cycle(CONECTIVOS_COMPLEMENTO[1:] + CONECTIVOS_COMPLEMENTO[:1])
        for j, (a, f) in enumerate(adicionais):
            r.citar_trecho(a, f, "resultado", "" if j == 0 else next(conectivos))
            if (j + 1) % 4 == 0:
                r.fechar()
        r.fechar()

    r.titulo(f"{n}.3 Interpretações e conclusões dos autores", 2)
    discussoes = [(a, next((f for f in a.discussoes if not r.ja_usada(a, f)), None)) for a in artigos]
    discussoes = [(a, f) for a, f in discussoes if f]
    if discussoes:
        r.frase("Na discussão de seus resultados, os autores propõem explicações para os efeitos observados.")
        conectivos = cycle(CONECTIVOS_DISCUSSAO)
        for j, (a, f) in enumerate(discussoes):
            r.citar_trecho(a, f, "discussao", next(conectivos) if j else "")
            if (j + 1) % 4 == 0:
                r.fechar()
        r.fechar()
    conclusoes = [(a, next((f for f in a.conclusoes if not r.ja_usada(a, f)), None)) for a in artigos]
    conclusoes = [(a, f) for a, f in conclusoes if f]
    if conclusoes:
        r.frase(f"Quanto às conclusões, {pl(len(conclusoes), 'estudo')} deste eixo {vb(len(conclusoes), 'explicita', 'explicitam')} as implicações de seus achados.")
        conectivos = cycle(CONECTIVOS_CONCLUSAO)
        for j, (a, f) in enumerate(conclusoes):
            r.citar_trecho(a, f, "conclusao", next(conectivos) if j else "")
            if (j + 1) % 4 == 0:
                r.fechar()
        r.fechar()

def _tema(r: Redator, tema: Tema, indice: int) -> None:
    artigos = [a for a, _ in tema.trechos]
    rotulo = _rotulo_tema(tema)
    grupo = r.citar_grupo(artigos)
    aberturas = [
        f"O tema {rotulo} é comum a {pl(len(artigos), 'estudo')} deste eixo {grupo}.",
        f"No que se refere a {rotulo}, {pl(len(artigos), 'estudo')} {grupo} {vb(len(artigos), 'traz', 'trazem')} achados que podem ser lidos em conjunto.",
        f"Os achados sobre {rotulo} aparecem em {pl(len(artigos), 'estudo')} {grupo}.",
        f"Outro ponto de contato entre os estudos diz respeito a {rotulo}, abordado em {pl(len(artigos), 'trabalho')} {grupo}.",
    ]
    r.frase(aberturas[indice % len(aberturas)])
    conectivos = cycle(CONECTIVOS_COMPLEMENTO if indice % 2 else CONECTIVOS_CONVERGENCIA)
    for j, (a, f) in enumerate(tema.trechos):
        r.citar_trecho(a, f, "resultado", "" if j == 0 else next(conectivos))
        if (j + 1) % 4 == 0 and j + 1 < len(tema.trechos):
            r.fechar()
    r.fechar()

def _consideracoes(r: Redator, artigos: list[Artigo], eixos: list[Eixo], n: int) -> None:
    total = len(artigos)
    r.titulo(f"{n} Considerações finais")
    r.frase(f"A leitura integrada {dos(total)} permite delinear um quadro consistente dos resultados reportados na literatura analisada.")
    for e in eixos:
        temas = [_rotulo_tema(t) for t in e.temas]
        if temas:
            r.frase(f"No eixo “{e.titulo}” ({pl(len(e.artigos), 'estudo')}), os resultados articulam-se em torno de {lista(temas)}, "
                    f"temas que reúnem achados de mais de um trabalho.")
        else:
            r.frase(f"No eixo “{e.titulo}” ({pl(len(e.artigos), 'estudo')}), os trabalhos trazem contribuições específicas, sem temas recorrentes entre eles.")
    r.fechar()

    analiticas = contar_tecnicas(artigos, "analitica")[:2]
    sens = contar_tecnicas(artigos, "sensorial")
    sens_dict = dict(sens)
    com_sensorial = sum(1 for a in artigos if any(t in sens_dict for t in a.tecnicas))
    consumidores = sens_dict.get("testes com consumidores", 0)
    ml = dict(contar_tecnicas(artigos, "estatistica")).get("aprendizado de máquina", 0)
    if analiticas:
        r.frase(f"Do ponto de vista metodológico, o conjunto é marcado pelo predomínio de {lista([f'{t} ({pl(k, ESTUDO)}, {_pct(k, total)})' for t, k in analiticas])}.")
    if sens:
        r.frase(f"A avaliação sensorial aparece em {pl(com_sensorial, 'estudo')} ({_pct(com_sensorial, total)}), e a participação de consumidores, em {consumidores} ({_pct(consumidores, total)}).")
    if ml:
        r.frase(f"Abordagens de aprendizado de máquina são empregadas em {pl(ml, 'estudo')}, sobretudo para classificação e predição.")
    r.fechar()
