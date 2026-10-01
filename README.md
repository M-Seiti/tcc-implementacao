# TCC — Indicadores de saúde e educação nos municípios de Minas Gerais

Pipeline reprodutível que extrai microdados públicos do DATASUS (SINASC, SIM,
CNES) e do INEP para MG no período 2010–2019, trata os dados, integra as
fontes num fato único e produz uma análise exploratória. Grão analítico:
**município × ano**.

## Estrutura

```
tcc-saude-educacao/
├── config.py           # caminhos e parâmetros do estudo (edite aqui)
├── extract.py          # saúde etapa 1: PySUS -> data/raw
├── transform.py        # saúde etapa 2: seleção de colunas + limpeza -> data/interim
├── eda.py              # saúde etapa 3: análise exploratória -> reports/figures
├── indicadores_saude.py # saúde etapa 4: indicadores município-ano -> data/processed
├── extract_edu.py      # educação etapa 1: lê xlsx/csv/zip do INEP em data/raw/edu -> data/raw
├── transform_edu.py    # educação etapa 2: limpeza + indicadores município-ano -> data/interim, data/processed
├── eda_edu.py           # educação etapa 3: análise exploratória -> reports/figures
├── merge_fontes.py     # integração: 6 etapas de qualidade -> data/processed/fato_indicadores.parquet
├── data/
│   ├── raw/            # cru, intocado (não versionado)
│   │   └── edu/         # arquivos do INEP baixados manualmente (entrada do extract_edu.py)
│   ├── interim/        # colunas selecionadas e limpas
│   └── processed/      # grão município-ano
├── reports/figures/    # gráficos gerados pela EDA
├── reports/qualidade/  # perfil das fontes e violações da validação (gerados pelo merge_fontes.py)
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
python indicadores_saude.py  # agrega -> data/processed/indicadores_saude_mg.parquet

# 2b. pipeline de EDUCAÇÃO
# baixe manualmente do portal do INEP as planilhas de IDEB (anos iniciais e
# finais) e do Censo Escolar (matrículas, distorção idade-série, rendimento)
# e coloque-as em data/raw/edu/ antes de rodar:
python extract_edu.py     # lê xlsx/csv/zip de data/raw/edu -> data/raw (parquet cru)
python transform_edu.py   # filtra MG, limpa, calcula os indicadores -> data/interim, data/processed
python eda_edu.py         # explora e gera as figuras

# 3. INTEGRAÇÃO saúde + educação (precisa dos dois parquets em data/processed)
python merge_fontes.py    # -> data/processed/fato_indicadores.parquet
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

### Indicadores de saúde (`indicadores_saude.py`)

Agrega `data/interim/sinasc_mg.parquet` e `sim_mg.parquet` no grão
município-ano (`cod_municipio_6` como texto + `ano`). Cada proporção usa como
denominador **só os nascimentos com a informação válida** daquele campo —
ignorado não entra nem no numerador nem no denominador.

| Indicador | Numerador | Denominador |
|-----------|-----------|-------------|
| `nascidos_vivos` | registros do SINASC (ano do nascimento) | — |
| `obitos_infantis` | óbitos do SIM com `obito_infantil` (0–364 dias; ano do óbito) | — |
| `tmi` | óbitos infantis × 1000 | nascidos vivos no mesmo município-ano |
| `prop_cesarea` | `PARTO = 2` | `PARTO` ∈ {1, 2} |
| `prop_baixo_peso` | peso < 2.500 g | peso plausível (200–7.000 g) |
| `prop_mae_adolescente` | idade da mãe ≤ 19 | idade plausível (10–60) |
| `prop_prenatal_adequado` | 7+ consultas (`CONSULTAS = 4`) | `CONSULTAS` ∈ {1..4} |
| `prop_mae_baixa_escolaridade` | menos de 8 anos de estudo (`ESCMAE` ∈ {1, 2, 3}) | `ESCMAE` ∈ {1..5} |

Proporções em **percentual (0–100)**. A TMI usa óbitos e nascimentos do mesmo
ano-calendário (forma direta, sem correção de sub-registro). Código de
município com 7 dígitos é reduzido a 6 tirando o verificador — a mesma ponte
do `merge_fontes.py`. Município-ano com óbito e sem nascido fica com TMI nula
(e o script avisa).

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

### Integração das fontes (`merge_fontes.py`)

Junta `indicadores_saude_mg.parquet` (DATASUS, chave `cod_municipio_6` +
`ano`) e `indicadores_educacao_mg.parquet` (INEP, chave `COD_MUNICIPIO` de 7
dígitos + `ano`) em `data/processed/fato_indicadores.parquet`, no grão
município-ano. Segue o processo de qualidade de dados em 6 etapas, nesta
ordem, e cada etapa imprime o que fez:

| # | Etapa | O que faz | Problema que pega |
|---|-------|-----------|-------------------|
| 1 | Profiling | Perfil por coluna de cada fonte **antes** de tocar nela: tipo, completude %, nº de distintos, unicidade %, min/mediana/max (numéricas) ou exemplos (textuais); reporta chave duplicada e chave lida como número. Salva em `reports/qualidade/perfil_fontes.csv`. | Diagnóstico — não altera dado. |
| 2 | Padronização | Código do município vira texto só com dígitos (tira o `.0` de leitura como float antes de tirar não-dígitos), com `zfill`; MG filtrado pelo **prefixo `31`** do código; `ano` vira inteiro e fica só 2010–2019. | Código salvo como número, município de outra UF infiltrado, ano como texto. |
| 3 | Deduplicação | Uma linha por chave em cada fonte, **antes** do merge, ficando com o primeiro valor não-nulo por coluna; avisa se as repetições tinham valores divergentes. | Chave repetida (que no merge vira explosão cartesiana). |
| 4 | Merge | *Append columns* com matching **determinístico exato** em `cod_municipio_6` + `ano`, `how="outer"`, `indicator=True`, `validate="1:1"`; reporta cobertura e municípios exclusivos de cada lado. | Município presente só numa fonte (fica visível, não some). |
| 5 | Survivorship | Regra por campo quando mais de uma fonte fornece o mesmo campo; conta conflitos reais e de qual fonte veio cada valor. | Conflito entre fontes (hoje não há — ver abaixo). |
| 6 | Validação | Invariantes do merge; se alguma quebra, o fato **não é salvo** e as violações vão para `reports/qualidade/violacoes_validacao.csv`. | Erro de merge que passaria em silêncio. |

**Decisões metodológicas:**

- **Chave como texto, nunca número.** Como número o código perde zero à
  esquerda e vira `3106200.0` quando lido como float; o join com a outra fonte
  então falha **em silêncio** (sobra `NaN`, não erro). Nenhum código IBGE
  começa com zero (UF vai de 11 a 53), mas o `zfill` fica como defesa.
- **Filtro de MG pelo prefixo `31`, nunca por campo de UF da fonte** — já
  comprovamos arquivos nacionais rotulados como estaduais. Mesma regra do
  `transform.py` e do `transform_edu.py`.
- **Deduplicação por "primeiro não-nulo", nunca soma nem média.** Chave
  repetida é registro repetido, não duas medições legítimas: somar dobraria
  nascidos e matrículas; fazer média inventaria um valor que nenhuma fonte
  publicou.
- **Método *append columns*.** As fontes descrevem **atributos diferentes** da
  mesma entidade (município-ano): saúde traz colunas de saúde, educação traz
  colunas de educação. Integrar é acrescentar colunas lado a lado, não empilhar
  linhas (*append rows*) nem fundir registros conflitantes.
- **Matching determinístico (exato), não fuzzy.** Existe identificador oficial
  e estável — o código IBGE do município. Fuzzy matching (por nome, por
  exemplo) só introduziria erro de pareamento (homônimos, grafias com e sem
  acento) onde não há ambiguidade a resolver. O `validate="1:1"` do pandas
  ainda garante que nenhuma chave casa com mais de uma linha.
- **Ponte 6→7 dígitos sem dígito verificador.** O código de 6 dígitos do
  DATASUS é o código IBGE de 7 **sem o último dígito** (o verificador). Em vez
  de calcular o verificador para estender o DATASUS, truncamos o lado do INEP
  (que já tem 7) para 6 e casamos por aí; o código de 7 que fica no fato é o
  **autêntico**, vindo do INEP. A ponte é conferida (um código de 6 → um único
  de 7, senão erro) e também completa o código de 7 nas linhas só-saúde de
  municípios que aparecem no INEP em outros anos. Município ausente do INEP em
  todos os anos fica com `cod_municipio` nulo até a entrada do IBGE.
- **Coluna `cobertura`** (`ambas` / `so_saude` / `so_educacao`) fica no fato,
  vinda do `indicator=True`, para a análise saber de onde veio cada linha.
- **Survivorship.** Registro configurável no topo de `merge_fontes.py`
  (`SURVIVORSHIP`, `ESTRATEGIA_PADRAO`, `ORDEM_CONFIANCA`), com duas
  estratégias:
  - `source_priority` — vale o valor da fonte mais confiável que estiver
    preenchida. Ordem de confiança para atributos de município:
    **IBGE > INEP > DATASUS** (o IBGE é o dono do cadastro de municípios).
  - `most_complete` — as fontes são ordenadas pela completude daquele campo
    (empate decidido pela ordem de confiança), e vale o primeiro valor
    preenchido nessa ordem.

  Para cada campo resolvido, imprime quantos **conflitos reais** houve (as
  duas fontes preenchidas e diferentes) e quantos valores vieram de cada
  fonte. **Hoje saúde e educação são complementares** — nenhum campo além da
  chave aparece nas duas —, então o script diz explicitamente que não há
  conflito, sem simular nenhum. As regras passam a valer quando o IBGE entrar
  como terceira fonte (nome, código de 7 dígitos, população). Ao resolver um
  campo, só são removidos os nomes **exatos** `<campo>_datasus` /
  `<campo>_inep`: remover por prefixo faria `cod_municipio` apagar também
  `cod_municipio_6`, a chave.
- **Invariantes da validação** — se quebram, o erro é do **merge**, não do dado:
  - (a) municípios distintos ≈ 853 (total de MG; aceita até 2% a menos, nunca
    a mais — mais de 853 é UF vazada, muito menos é join falhando em silêncio);
  - (b) zero chave `cod_municipio_6` + `ano` duplicada no resultado;
  - (c) nº de linhas no máximo 30% acima da maior fonte (guarda contra
    explosão cartesiana);
  - (d) faixas plausíveis: IDEB em [0, 10]; taxas e proporções percentuais em
    [0, 100]; contagens ≥ 0; TMI em [0, 1000].
- **TMI acima de 100 por mil não é erro.** Em município minúsculo, 1 óbito em
  5 nascidos dá 200 por mil — aritmética correta. Por isso o teto da TMI é
  1000, e o script só emite uma **nota informativa** (não falha) com quantos
  município-ano têm menos de 100 nascidos vivos: é instabilidade de número
  pequeno, a ser tratada com **filtro de porte na análise**, não na integração.

## Próximas etapas (ainda não no código)

1. Trazer a tabela do IBGE (código de 7 dígitos + população por município-ano)
   — vale tanto para saúde (hoje em 6 dígitos) quanto para completar a dimensão
   de município da educação.
2. Baixar os arquivos reais do INEP em `data/raw/edu/` e validar/ajustar os
   nomes de coluna candidatos em `transform_edu.py` contra o layout real.
3. Trazer a proxy socioeconômica (IDHM) para a análise de confounding.
4. Modelar em **star schema** no PostgreSQL (`fato_indicadores`, já gerado
   pelo `merge_fontes.py`, + `dim_municipio`, `dim_tempo`) e carregar o
   `processed`.
5. Dashboard (Streamlit) sobre o resultado da análise.
