"""Configuração da Execução."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


# Constantes
"""Versão do pacote e tipos de entrada aceitos."""

VERSAO = "4.1"
TIPOS = {"pdf": "PDF", "ris": "RIS", "md": "MD"}


# Parâmetros
"""Entrada, saída, títulos, glossário e opções."""
@dataclass
class Config:
    tipo: str = "pdf"
    pasta_entrada: Path = Path(".")
    nome_output: str = "resultados_leitura"
    pasta_output: Path | None = None
    nome_documento: str = ""
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
    glossario: Path | None = None

    @property
    def titulo(self) -> str:
        return self.nome_documento or self.nome_output.replace("_", " ").strip()
