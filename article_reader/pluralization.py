"""Plural no CMD."""

from __future__ import annotations


# Auxiliares
def pl(n: int, singular: str, plural: str | None = None) -> str:
    """pl(1, "arquivo") -> "1 arquivo";  pl(3, "arquivo") -> "3 arquivos";
    pl(2, "arquivo lido", "arquivos lidos") -> "2 arquivos lidos"."""
    return f"{n} {singular if n == 1 else (plural or _plural(singular))}"

def vb(n: int, singular: str, plural: str) -> str:
    return singular if n == 1 else plural

def _plural(palavra: str) -> str:
    if palavra.endswith(("ão",)):
        return palavra[:-2] + "ões"
    if palavra.endswith("l") and not palavra.endswith("il"):
        return palavra[:-1] + "is"
    if palavra.endswith(("r", "z")):
        return palavra + "es"
    if palavra.endswith("m"):
        return palavra[:-1] + "ns"
    if palavra.endswith("s"):
        return palavra
    return palavra + "s"

def dos(n: int, singular: str = "estudo", plural: str | None = None) -> str:
    """dos(1) -> "do estudo";  dos(2) -> "dos 2 estudos"."""
    return f"do {singular}" if n == 1 else f"dos {n} {plural or _plural(singular)}"
