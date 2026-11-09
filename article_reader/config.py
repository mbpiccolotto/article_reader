"""Configuração central"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

VERSAO = "4.1"
TIPOS = {"pdf": "PDF", "ris": "RIS", "md": "MD"}


@dataclass #
class Config:
#input
    tipo: str = "pdf"                         
    pasta_entrada: Path = Path(".")          
#output
    nome_output: str = "resultados_leitura"
    pasta_output: Path | None = None         
    nome_documento: str = ""
#artigos/leitura
    resultados: int = 4
    discussoes: int = 2
    conclusoes: int = 1
    min_palavras: int = 5
    max_palavras: int = 100
    citacao: int = 40         
    tabelas: bool = True
    figuras: int = 20              
    dpi_figuras: int = 300
    min_eixos: int = 2
    max_eixos: int = 10
    min_artigos: int = 2
    max_temas: int = 10
#parâmetros
    glossario: Path | None = None             
    extras: dict = field(default_factory=dict)

    @property
    def titulo(self) -> str:
        return self.nome_documento or self.nome_output.replace("_", " ").strip()
