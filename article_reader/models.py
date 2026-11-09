"""Modelo de dados."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


# Classes
@dataclass
class Autor:
    sobrenome: str
    prenomes: str = ""

@dataclass
class Metadados:
    autores: list[Autor] = field(default_factory=list)
    ano: str = ""
    titulo: str = ""
    periodico: str = ""
    volume: str = ""
    numero: str = ""
    pagina_inicial: str = ""
    pagina_final: str = ""
    doi: str = ""
    palavras_chave: list[str] = field(default_factory=list)
    resumo: str = ""
    fonte: str = ""

    @property
    def paginas(self) -> str:
        if self.pagina_inicial and self.pagina_final and self.pagina_final != self.pagina_inicial:
            return f"{self.pagina_inicial}-{self.pagina_final}"
        return self.pagina_inicial

@dataclass
class Frase:
    texto: str
    pagina: int
    categoria: str
    secao: str
    ordem: int
    pontuacao: float = 0.0
    sentido: str = ""

@dataclass
class Artigo:
    arquivo: str
    metadados: Metadados
    categorias_encontradas: list[str] = field(default_factory=list)
    resultados: list[Frase] = field(default_factory=list)
    discussoes: list[Frase] = field(default_factory=list)
    conclusoes: list[Frase] = field(default_factory=list)
    candidatas: list[Frase] = field(default_factory=list)
    tecnicas: list[str] = field(default_factory=list)
    alertas: list[str] = field(default_factory=list)
    chave: str = ""
    sufixo_ano: str = ""
    iniciais_na_citacao: bool = False
    deslocamento_pagina: int = 0

    def para_dict(self) -> dict:
        return asdict(self)