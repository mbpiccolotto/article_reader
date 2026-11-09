"""Menu e verificação de dependências."""

from __future__ import annotations

import argparse
import importlib
import importlib.util
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


# Verificação de dependências
DEPENDENCIAS = {
    "pymupdf": "pymupdf>=1.26",
    "sklearn": "scikit-learn>=1.3",
    "numpy": "numpy>=1.24",
    "docx": "python-docx>=1.1",
}
TIPOS = {"1": "pdf", "2": "ris", "3": "md"}
NOMES = {"pdf": "PDF", "ris": "RIS", "md": "MD"}

def garantir_dependencias(dependencias: dict = DEPENDENCIAS, arquivo_req: str = "requirements.txt") -> None:
    faltando = [req for mod, req in dependencias.items() if importlib.util.find_spec(mod) is None]
    if not faltando:
        return
    print(f"Instalando dependências que faltam: {', '.join(faltando)}")
    requisitos = Path(__file__).resolve().parent.parent / arquivo_req
    comando = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "-q"]
    comando += ["-r", str(requisitos)] if requisitos.exists() else faltando
    resultado = subprocess.run(comando)
    importlib.invalidate_caches()
    ainda = [req for mod, req in dependencias.items() if importlib.util.find_spec(mod) is None]
    if resultado.returncode != 0 or ainda:
        raise SystemExit("\nNão foi possível instalar: " + ", ".join(ainda or faltando)
                         + f"\nTente manualmente: {sys.executable} -m pip install " + " ".join(ainda or faltando))


# Módulos
MODULOS = [
    ("NumPy", "numpy"),
    ("scikit-learn", "sklearn.cluster"),
    ("scikit-learn", "sklearn.feature_extraction.text"),
    ("scikit-learn", "sklearn.decomposition"),
    ("scikit-learn", "sklearn.metrics"),
    ("PyMuPDF", "pymupdf"),
    ("python-docx", "docx"),
    ("leitor", "article_reader.pipeline"),
]

def carregar_modulos() -> None:
    """Loading dos módulos."""
    from .progress_bar import BarraProgresso

    barra = BarraProgresso(len(MODULOS), "Carregando")
    for rotulo, modulo in MODULOS:
        importlib.import_module(modulo)
        barra.avancar(rotulo)
    barra.fim()


# Seleção de leitura
def escolher_pasta(tipo: str) -> Path | None:
    """Selecione a pasta de arquivos."""
    try:
        import tkinter
        from tkinter import filedialog

        raiz = tkinter.Tk()
        raiz.withdraw()
        raiz.attributes("-topmost", True)
        raiz.update()
        try:
            escolha = filedialog.askdirectory(parent=raiz, mustexist=True,
                                              title=f"Selecione a pasta de arquivos {NOMES[tipo]}")
        finally:
            raiz.destroy()
        return Path(escolha) if escolha else None
    except Exception:
        from .console_input import ler_linha

        texto = ler_linha("Caminho da pasta (vazio = voltar ao início)").strip().strip('"')
        return Path(texto) if texto else None

def abrir_no_explorador(arquivo: Path) -> None:
    if os.name == "nt":
        try:
            subprocess.Popen(["explorer", "/select,", str(arquivo)])
        except OSError:
            pass


# Leitura e Menu
CABECALHO = """
================================================================
 Leitor de artigos {extra}
================================================================
 Ctrl+R = Nova Leitura  |   Ctrl+C = Sair
"""

def uma_leitura(nova: bool) -> None:
    from . import progress_bar as progresso
    from .config import Config
    from .pluralization import pl
    from .console_input import CTRL_R, Monitor, NovaLeitura, escolher, getch, ler_linha
    from .pipeline import executar, listar_arquivos

    print(CABECALHO.format(extra=" — NOVA LEITURA" if nova else ""))
    print("Leitor de artigos, selecione o tipo de arquivo (digite o número):")
    print("  1. PDF")
    print("  2. RIS")
    print("  3. MD")
    print("> ", end="", flush=True)
    tipo = TIPOS[escolher("123")]

    while True:
        print(f"\nSelecione a pasta de arquivos ({NOMES[tipo]}): Carregando...", flush=True)
        pasta = escolher_pasta(tipo)
        if pasta is None:
            print("  Seleção cancelada.")
            raise NovaLeitura
        if not pasta.is_dir():
            print(f"  Pasta não encontrada: {pasta}")
            continue
        arquivos = listar_arquivos(pasta, tipo)
        if arquivos:
            break
        print(f"  Nenhum arquivo {NOMES[tipo]} em {pasta} (subpastas incluídas). Selecione outra pasta.")

    extra = ""
    if tipo != "ris":
        n_ris = len(listar_arquivos(pasta, "ris"))
        extra = (f" + {pl(n_ris, 'arquivo RIS', 'arquivos RIS')} para os metadados" if n_ris
                 else "; não há arquivos RIS para os metadados")
    print(f"Pasta: {pasta}\n  {pl(len(arquivos), f'arquivo {NOMES[tipo]}', f'arquivos {NOMES[tipo]}')}{extra}.")

    padrao = f"leitura_{tipo}_{datetime.now():%Y-%m-%d_%Hh%M}"
    nome = ""
    while not nome:
        nome = ler_linha("\nSelecione o nome dos resultados", padrao).strip()
    cfg = Config(tipo=tipo, pasta_entrada=pasta, nome_output=nome)

    print("\nProcessando... (Ctrl+R relaunch; Ctrl+C exit)\n", flush=True)
    with Monitor() as monitor:
        progresso.VERIFICAR = monitor.verificar
        try:
            zip_final = executar(cfg)
        finally:
            progresso.VERIFICAR = None
    abrir_no_explorador(zip_final)
    print("\nCtrl+R ou Enter = nova leitura   |   Ctrl+C = sair", flush=True)
    while True:
        if getch() in (CTRL_R, "\r", "\n"):
            raise NovaLeitura

def interativo() -> None:
    from .console_input import NovaLeitura, preparar_console, restaurar_console, sair

    preparar_console()
    nova = False
    try:
        while True:
            try:
                uma_leitura(nova)
            except NovaLeitura:
                pass
            except PermissionError as erro:
                print(f"\nSem permissão para acessar: {erro.filename}\n"
                      "Feche o arquivo e tente novamente.")
            except RuntimeError as erro:
                print(f"\nErro: {erro}")
            nova = True
    except KeyboardInterrupt:
        sair()
    finally:
        restaurar_console()


# Comando
def main(argv: list[str] | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8") #type: ignore
        except (AttributeError, ValueError):
            pass
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["analisar"]:
        garantir_dependencias({"pandas": "pandas", "scipy": "scipy", "matplotlib": "matplotlib", "openpyxl": "openpyxl",
                               "xlsxwriter": "XlsxWriter", "PIL": "Pillow", "pymupdf": "pymupdf"},
                               "requirements.txt")
        from .meta_analysis import main as main_analises

        return main_analises(argv[1:])

    parser = argparse.ArgumentParser(
        prog="python -m article_reader",
        description="Lê artigos (PDF, RIS ou MD) e gera, em um .zip, o resumo integralizado e a ficha e relatório de "
                    "leitura em .docx, com citações diretas e referências ABNT. Sem argumentos, abre o menu.")
    parser.add_argument("pasta", nargs="?", help="Pasta com os arquivos")
    parser.add_argument("--tipo", choices=["pdf", "ris", "md"], help="Tipo de arquivo da pasta")
    parser.add_argument("--nome", help="Nome dos resultados")
    parser.add_argument("--destino", type=Path, help="Pasta do .zip")
    parser.add_argument("--titulo", default="", help="Título do resumo (padrão: o nome dos resultados)")
    parser.add_argument("--glossario", type=Path, help="CSV termo_en;termo_pt para traduzir nomes de eixos e temas")
    parser.add_argument("--sem-tabelas", action="store_true", help="Não extrai tabelas dos PDFs (mais rápido)")
    args = parser.parse_args(argv)

    print("Iniciando...", flush=True)
    garantir_dependencias()
    carregar_modulos()
    if not args.pasta:
        interativo()
        return 0
    if not args.tipo or not args.nome:
        parser.error("no modo por argumentos, informe --tipo e --nome")
    from .config import Config
    from .pipeline import executar

    cfg = Config(tipo=args.tipo, pasta_entrada=Path(args.pasta).expanduser().resolve(), nome_output=args.nome,
                 pasta_output=args.destino, nome_documento=args.titulo, glossario=args.glossario,
                 tabelas=not args.sem_tabelas)
    try:
        executar(cfg)
    except KeyboardInterrupt:
        print("\nInterrompido.")
        return 130
    except (RuntimeError, PermissionError) as erro:
        print(f"\nErro: {erro}")
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())