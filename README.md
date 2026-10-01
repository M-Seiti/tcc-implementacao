# TCC — Indicadores de saúde e educação nos municípios de Minas Gerais

Pipeline reprodutível que extrai microdados públicos do DATASUS (SINASC, SIM,
CNES) para MG no período 2010–2019, trata os dados e produz uma análise
exploratória. Grão analítico: **município × ano**.

## Estrutura

```
tcc-saude-educacao/
├── config.py           # caminhos e parâmetros do estudo (edite aqui)
├── extract.py          # saúde etapa 1: PySUS -> data/raw
├── transform.py        # saúde etapa 2: seleção de colunas + limpeza -> data/interim
├── eda.py              # saúde etapa 3: análise exploratória -> reports/figures
├── extract_edu.py      # educação etapa 1: lê xlsx/csv/zip do INEP em data/raw/edu -> data/raw
├── transform_edu.py    # educação etapa 2: limpeza + indicadores município-ano -> data/interim, data/processed
├── eda_edu.py           # educação etapa 3: análise exploratória -> reports/figures
├── data/
│   ├── raw/            # cru, intocado (não versionado)
│   │   └── edu/         # arquivos do INEP baixados manualmente (entrada do extract_edu.py)
│   ├── interim/        # colunas selecionadas e limpas
│   └── processed/      # grão município-ano
├── reports/figures/    # gráficos gerados pela EDA
├── requirements.txt
└── .gitignore          # ignora data/ — dados são recriáveis pelo código
```

## Como rodar

```bash
# 1. ambiente
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt

# 2a. pipeline de SAÚDE (rode a partir da RAIZ do projeto)
python extract.py         # baixa do DATASUS (só a 1ª vez é lenta; depois usa cache)
python transform.py       # limpa
python eda.py             # explora e gera as figuras

# 2b. pipeline de EDUCAÇÃO
# baixe manualmente do portal do INEP as planilhas de IDEB (anos iniciais e
# finais) e do Censo Escolar (matrículas, distorção idade-série, rendimento)
# e coloque-as em data/raw/edu/ antes de rodar:
python extract_edu.py     # lê xlsx/csv/zip de data/raw/edu -> data/raw (parquet cru)
python transform_edu.py   # filtra MG, limpa, calcula os indicadores -> data/interim, data/processed
python eda_edu.py         # explora e gera as figuras
```

> Rode sempre da raiz do projeto. Os módulos ficam na raiz (não em `src/`), então
> os imports são `from config import ...` e os caminhos relativos partem daqui.

## Decisões de método já embutidas no código

- **Janela 2010–2019** — recorte de cobertura consolidada (evita a lacuna de
  anos e a distorção da COVID). Ajustável em `config.py`.
- **`raw` é sagrado** — a extração salva todas as colunas, intocadas. Seleção e
  limpeza só a partir do `interim`.
- **Memória** — a extração processa um sistema por vez e libera a RAM; o CNES
  tem ~362 colunas e derruba o kernel se tudo ficar carregado junto.
- **Códigos de "ignorado" → NaN** — para não contaminarem médias e proporções.
  O sentinela varia por campo (ver `IGNORADO_SINASC` em `config.py`).
- **SIM: `TIPOBITO=2`** — só óbitos não-fetais entram na mortalidade infantil.
- **Idade pela diferença de datas** — `DTOBITO − DTNASC`, mais confiável que o
  campo `IDADE` codificado. `between(0, 364)` descarta datas invertidas.
- **Município em 6 dígitos por enquanto** — a expansão para o código IBGE de 7
  dígitos acontece no join com a tabela oficial do IBGE (nunca calculando o
  dígito verificador), que também trará a população (denominador).

### Educação (INEP)

- **Sem biblioteca de download** — diferente do PySUS, não existe API/pacote
  para o INEP. Os arquivos (`xlsx`/`csv`/`zip`) são baixados manualmente do
  portal e colocados em `data/raw/edu/` antes de rodar `extract_edu.py`.
- **`raw` fica nacional, não filtrado** — os arquivos do INEP não têm um
  parâmetro de UF como o PySUS; o `extract_edu.py` só lê e converte para
  parquet, sem filtrar. O filtro de MG (prefixo `31` do código do município)
  acontece só no `transform_edu.py`, igual à regra 1 da saúde.
- **Município em 7 dígitos** — o INEP usa o código IBGE completo (7 dígitos),
  diferente dos 6 do DATASUS. Nunca calculamos dígito verificador.
- **Nome de coluna muda entre edições do INEP, não só de caixa** — por isso
  `transform_edu.py` usa listas de nomes candidatos (`COLS_CANDIDATAS_*` em
  `config.py`) e funde com `combine_first` (`_fundir_por_candidatos`), em vez
  de assumir um nome de coluna fixo.
- **IDEB é bienal** — só existe em 2011, 2013, 2015, 2017, 2019. Nos anos
  pares, as colunas `IDEB_ANOS_INICIAIS`/`IDEB_ANOS_FINAIS` ficam `NaN` de
  propósito no `indicadores_educacao_mg.parquet` — não é erro de junção.
- **Distorção/rendimento agregados por média simples** — as fontes do INEP
  costumam vir quebradas por etapa/série; simplificamos para uma média por
  município-ano (`_agregar_municipio_ano`). Documentado no código caso a
  análise precise abrir por etapa depois.
- **⚠️ Nomes de coluna ainda não validados contra arquivos reais** — como os
  arquivos do INEP ainda não foram baixados neste projeto, as listas de
  candidatos em `config.py` e nas funções `tratar_*` de `transform_edu.py`
  são um ponto de partida baseado no padrão conhecido do INEP. A lógica foi
  testada com arquivos sintéticos que imitam as manhas do formato (linhas de
  título antes do cabeçalho, nomes de coluna diferentes entre edições,
  sentinelas), mas precisa ser conferida assim que os arquivos reais
  chegarem em `data/raw/edu/` — o código falha com um erro claro (listando
  as colunas disponíveis) em vez de seguir com a coluna errada.

## Próximas etapas (ainda não no código)

1. Trazer a tabela do IBGE (código de 7 dígitos + população por município-ano)
   — vale tanto para saúde (hoje em 6 dígitos) quanto para completar a dimensão
   de município da educação.
2. **Agregar saúde** para o grão município-ano: taxa de mortalidade infantil, %
   cesárea, % baixo peso, gravidez na adolescência, cobertura pré-natal.
3. Baixar os arquivos reais do INEP em `data/raw/edu/` e validar/ajustar os
   nomes de coluna candidatos em `transform_edu.py` contra o layout real.
4. Trazer a proxy socioeconômica (IDHM) para a análise de confounding.
5. Modelar em **star schema** no PostgreSQL (`fato_indicadores`,
   `dim_municipio`, `dim_tempo`) e carregar o `processed`.
6. Dashboard (Streamlit) sobre o resultado da análise.
