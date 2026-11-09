# Leitor de artigos

Lê artigos científicos (PDF, referências RIS ou texto Markdown) e gera, em um .zip:

- **resumo integralizado** (.docx): síntese organizada em eixos temáticos, com citações diretas dos artigos (ABNT NBR 10520:2023 e 6023:2018);
- **ficha e relatório de leitura** (.docx): uma ficha por artigo (metadados, trechos selecionados, alertas) e o relatório da execução.

## Como usar

1. Instale o Python 3.10 ou mais novo (python.org).
2. Dê dois cliques em `launch.bat` (instala o que faltar) e siga o menu: tipo de entrada (1 PDF, 2 RIS, 3 MD), pasta e nome.
3. Ou, pelo terminal: `python -m article_reader PASTA --tipo pdf --nome MeuResumo --destino SAIDA`.

Se houver arquivos `.ris` na mesma pasta dos PDFs, eles fornecem autores, ano e periódico (sem RIS, a citação sai só com o título).

## Módulos (`article_reader/`)

| Arquivo | Função |
| --- | --- |
| `__main__.py` | Ponto de entrada: menu interativo, opções de linha de comando e verificação de dependências |
| `pipeline.py` | Orquestra as cinco etapas da leitura, descarta duplicatas e gera o .zip |
| `document_reader.py` | Lê o PDF (texto, colunas, tabelas, figuras), repara palavras coladas e ligaduras, detecta OCR |
| `section_parser.py` | Divide o texto em seções e frases (resultados, discussão, conclusão) |
| `metadata.py` | Lê RIS (UTF-8/UTF-16/Windows-1252) e associa cada registro ao PDF (cabeçalho com DOI, título, nome do arquivo) |
| `passage_selection.py` | Escolhe os trechos de cada artigo e detecta técnicas |
| `thematic_axes.py` | Agrupa os artigos em eixos e temas (TF-IDF + LSA + k-médias) |
| `summary_writer.py`, `citations.py`, `docx_builder.py` | Redação, citações ABNT e geração dos .docx |
| `meta_analysis.py` | Extração e análise quantitativa (uso opcional: `python -m article_reader analisar ...`) |
| `config.py`, `models.py`, `glossary.py`, `file_io.py`, `pluralization.py`, `progress_bar.py`, `console_input.py` | Configuração, modelos de dados, glossário, acesso a arquivos (caminhos longos), plural, barra de progresso e teclado |

## Limites conhecidos

- Os critérios de escolha de trechos e os rótulos de eixos são regras estatísticas e de palavras-chave, **não** compreensão do texto: confira sempre as citações no PDF.
- Funciona melhor com artigos em inglês, português ou espanhol e com a estrutura usual (Introdução, Métodos, Resultados, Discussão, Conclusão).
- A lista de "técnicas detectadas" e o glossário de tradução de termos (`glossary.py`) foram montados para química/ciência de alimentos; em outras áreas esses campos ficam vazios ou sem tradução (use `--glossario arquivo.csv`, com `termo_en;termo_pt`, para acrescentar termos).
- PDFs escaneados dependem da camada de OCR do arquivo; o texto é marcado com alerta.
