# Documentação do projeto

**Indicadores de saúde e educação nos municípios de Minas Gerais (2010–2019)**

Pipeline de dados que integra microdados do DATASUS (saúde materno-infantil) e indicadores do
INEP (educação básica) no grão **município × ano**, aplica um processo de qualidade de dados em
6 etapas e analisa a associação entre as duas áreas com correlação de Spearman, apresentada num
BI em Streamlit.

Este documento reúne o que foi feito, como foi feito e **por quê**: arquitetura, tratamento das
fontes, integração, método estatístico, resultados, decisões de escopo e limitações. O
`README.md` na raiz é o guia rápido de instalação e execução.

---

## Sumário

1. [Objetivo e escopo](#1-objetivo-e-escopo)
2. [Fontes de dados](#2-fontes-de-dados)
3. [Arquitetura](#3-arquitetura)
4. [Como executar](#4-como-executar)
5. [Tratamento das fontes](#5-tratamento-das-fontes)
6. [Indicadores](#6-indicadores)
7. [Integração das fontes: as 6 etapas de qualidade](#7-integração-das-fontes-as-6-etapas-de-qualidade)
8. [Análise estatística](#8-análise-estatística)
9. [As 5 combinações analisadas](#9-as-5-combinações-analisadas)
10. [Resultados](#10-resultados)
11. [Visualização: figuras e BI](#11-visualização-figuras-e-bi)
12. [Decisões de escopo](#12-decisões-de-escopo)
13. [Limitações](#13-limitações)
14. [Trabalhos futuros](#14-trabalhos-futuros)
15. [Referências](#15-referências)

---

## 1. Objetivo e escopo

**Pergunta de pesquisa:** nos municípios de Minas Gerais, indicadores de saúde materno-infantil
e de educação básica estão associados?

| Dimensão | Escopo |
|---|---|
| Território | os 853 municípios de Minas Gerais |
| Período | 2010–2019 (cobertura consolidada das fontes, antes da distorção da COVID) |
| Grão analítico | município × ano (8.530 combinações) |
| Saúde | nascimentos (SINASC) e óbitos (SIM) do DATASUS |
| Educação | IDEB, matrículas, distorção idade-série e rendimento escolar do INEP |
| Análise | correlação de Spearman em 5 combinações definidas previamente, sem controle socioeconômico |
| Entrega visual | figuras estáticas para o texto e BI interativo em Streamlit |

---

## 2. Fontes de dados

| Fonte | Órgão | O que traz | Como é obtida | Código do município |
|---|---|---|---|---|
| **SINASC** | Ministério da Saúde / DATASUS | um registro por nascido vivo | biblioteca PySUS (`extract.py`) | 6 dígitos |
| **SIM** | Ministério da Saúde / DATASUS | um registro por óbito | biblioteca PySUS (`extract.py`) | 6 dígitos |
| **CNES** | Ministério da Saúde / DATASUS | estabelecimentos de saúde (mês de dezembro) | biblioteca PySUS (`extract.py`) | 6 dígitos |
| **IDEB** | INEP / MEC | índice de qualidade do ensino fundamental, por município | planilha baixada manualmente do portal | 7 dígitos |
| **Censo Escolar** | INEP / MEC | matrículas, distorção idade-série, abandono e reprovação | planilhas baixadas manualmente do portal | 7 dígitos |

O CNES é extraído, mas **não é usado na análise** (justificativa na [seção 12.2](#122-cnes-fora-da-análise)).

**Por que o código do município muda de tamanho:** o código IBGE do município tem 7 dígitos,
sendo o último um dígito verificador. O DATASUS usa só os 6 primeiros; o INEP usa os 7. A
integração resolve isso sem calcular o dígito verificador (ver [seção 7.4](#74-etapa-4--merge)).

---

## 3. Arquitetura

### 3.1 Arquitetura medalhão

O projeto segue a **arquitetura medalhão** (bronze → silver → gold), com as camadas nomeadas
`raw`, `interim` e `processed`:

| Camada medalhão | Pasta | Conteúdo | Regra |
|---|---|---|---|
| **Bronze** (cru) | `data/raw/` | dados como vieram das fontes, sem filtro nem limpeza | nunca é alterada; tudo é recriável a partir dela |
| **Silver** (limpo) | `data/interim/` | colunas selecionadas, "ignorado" → nulo, só MG, código de município padronizado | só lê do bronze |
| **Gold** (consumo) | `data/processed/` | indicadores município-ano, o fato integrado e a base da análise | só lê do silver ou do próprio gold; alimenta a análise e o BI |

A pasta `data/` não é versionada (está no `.gitignore`): os dados são pesados e recriáveis pelo
código.

### 3.2 Fluxo dos dados

```
                  BRONZE (data/raw)          SILVER (data/interim)       GOLD (data/processed)
DATASUS ──extract.py──► sinasc, sim, cnes ──transform.py──► sinasc, sim ──indicadores_saude.py──► indicadores_saude_mg ──┐
                                                                                                                        ├─merge_fontes.py─► fato_indicadores ─┬─► figuras_integracao.py
INEP ──extract_edu.py──► ideb, matrículas, ──transform_edu.py──► *_mg ─────────────────────────► indicadores_educacao_mg ┘                                    ├─► correlacoes.py ─► municipio_periodo, correlacoes_*
                         distorção, rendimento                                                                                                               └─► app_bi.py (BI)
```

### 3.3 Arquivos do projeto

| Arquivo | Etapa | Lê | Gera |
|---|---|---|---|
| `config.py` | configuração | — | caminhos, período, colunas e parâmetros usados por todos os scripts |
| `extract.py` | saúde: extração | DATASUS (PySUS) | `data/raw/sinasc_mg`, `sim_mg`, `cnes_mg` |
| `transform.py` | saúde: limpeza | `data/raw` | `data/interim/sinasc_mg`, `sim_mg` |
| `indicadores_saude.py` | saúde: indicadores | `data/interim` | `data/processed/indicadores_saude_mg.parquet` |
| `extract_edu.py` | educação: extração | planilhas em `data/raw/edu/` | `data/raw/ideb_*`, `matriculas`, `distorcao`, `rendimento` |
| `transform_edu.py` | educação: limpeza e indicadores | `data/raw` | `data/interim/*_mg`, `data/processed/indicadores_educacao_mg.parquet`, `dim_municipio_edu_mg.parquet` |
| `merge_fontes.py` | integração (6 etapas) | os dois `indicadores_*_mg` | `data/processed/fato_indicadores.parquet`, `reports/qualidade/` |
| `figuras_integracao.py` | visualização da integração | `fato_indicadores` | `reports/figures/integracao_*.png` |
| `correlacoes.py` | análise estatística | `fato_indicadores` | `data/processed/municipio_periodo.parquet`, `correlacoes_*.csv`, `reports/figures/correlacoes_*.png` |
| `app_bi.py` | BI interativo | `fato_indicadores` | painel no navegador |
| `eda.py`, `eda_edu.py`, `analises.py` | análise exploratória (opcional) | `data/interim` | `reports/figures/` |

---

## 4. Como executar

### 4.1 Ambiente

```powershell
python -m venv .venv
.venv\Scripts\activate          # Windows (Linux/Mac: source .venv/bin/activate)
pip install -r requirements.txt
```

Antes da etapa de educação, baixe manualmente do portal do INEP as planilhas de IDEB (anos
iniciais e finais) e do Censo Escolar (sinopse de matrículas, distorção idade-série e
rendimento) e coloque-as em `data/raw/edu/`.

### 4.2 Ordem de execução

Sempre a partir da raiz do projeto:

| # | Comando | Depende de |
|---|---|---|
| 1 | `python extract.py` | internet (DATASUS) |
| 2 | `python transform.py` | 1 |
| 3 | `python indicadores_saude.py` | 2 |
| 4 | `python extract_edu.py` | planilhas em `data/raw/edu/` |
| 5 | `python transform_edu.py` | 4 |
| 6 | `python merge_fontes.py` | 3 e 5 |
| 7 | `python figuras_integracao.py` | 6 |
| 8 | `python correlacoes.py` | 6 |
| 9 | `streamlit run app_bi.py` | 6 (abre em http://localhost:8501) |

Saúde (1–3) e educação (4–5) são independentes entre si. As etapas 7, 8 e 9 dependem só da 6.
Com `data/raw` e `data/interim` já prontos, basta rodar da etapa 3 em diante.

---

## 5. Tratamento das fontes

### 5.1 Saúde (`transform.py`)

| Regra | Por quê |
|---|---|
| Filtra MG pelo **prefixo `31` do código do município**, nunca pelo campo de UF | já foram encontrados arquivos nacionais rotulados como estaduais; o prefixo do código IBGE é a única garantia |
| Códigos de "ignorado" viram nulo, com o sentinela de cada campo (ex.: `ESCMAE` 9 e 0; `CONSULTAS` 9) | um "9 = ignorado" tratado como valor contaminaria médias e proporções |
| No SIM, só óbitos com `TIPOBITO = 2` | exclui óbitos fetais; a mortalidade infantil conta só nascidos vivos |
| Idade ao óbito pela diferença `DTOBITO − DTNASC`, e óbito infantil = 0 a 364 dias | mais confiável que o campo `IDADE` codificado; o intervalo descarta datas invertidas |
| Leitura em lotes e só das colunas necessárias | o CNES tem ~362 colunas e esgota a memória se lido inteiro |
| `raw` intocado | permite refazer qualquer limpeza sem baixar de novo |

### 5.2 Educação (`transform_edu.py`)

| Regra | Por quê |
|---|---|
| Nomes de coluna buscados numa **lista de candidatos** e fundidos | o nome do mesmo campo muda entre edições do INEP (ex.: `CO_MUNICIPIO` em um ano, "Código do Município" em outro) |
| Cabeçalho localizado pela célula com o nome exato da coluna de código | as planilhas têm título e cabeçalhos mesclados antes dos dados |
| Filtro de MG pelo prefixo `31`, depois de padronizar o código | mesma regra da saúde |
| Distorção e rendimento: só a linha **Total (localização) × Total (rede)** | as planilhas trazem subtotais por urbana/rural e por rede; misturá-los com o total distorceria a média |
| IDEB: rede **pública** | o IDEB municipal não tem rede "Total"; a pública é o recorte usual |
| IDEB nos anos pares fica nulo | o IDEB é **bienal** (2011, 2013, 2015, 2017, 2019); não é falha de junção |
| Falha com erro claro, listando as colunas disponíveis | melhor parar do que seguir com a coluna errada |

---

## 6. Indicadores

### 6.1 Saúde (`indicadores_saude.py`)

Agregados por município e ano a partir do SINASC e do SIM. Nas proporções, o denominador é
**só o conjunto de nascimentos com a informação válida** daquele campo: um registro "ignorado"
não entra nem no numerador nem no denominador.

| Indicador | Numerador | Denominador |
|---|---|---|
| `nascidos_vivos` | registros do SINASC (ano do nascimento) | — |
| `obitos_infantis` | óbitos do SIM com 0 a 364 dias de vida (ano do óbito) | — |
| `tmi` (por mil) | óbitos infantis × 1000 | nascidos vivos no mesmo município-ano |
| `prop_cesarea` (%) | `PARTO = 2` | `PARTO` ∈ {1, 2} |
| `prop_baixo_peso` (%) | peso < 2.500 g | peso plausível (200 a 7.000 g) |
| `prop_mae_adolescente` (%) | idade da mãe ≤ 19 anos | idade plausível (10 a 60 anos) |
| `prop_prenatal_adequado` (%) | 7 ou mais consultas (`CONSULTAS = 4`) | `CONSULTAS` ∈ {1, 2, 3, 4} |
| `prop_mae_baixa_escolaridade` (%) | menos de 8 anos de estudo (`ESCMAE` ∈ {1, 2, 3}) | `ESCMAE` ∈ {1, …, 5} |

Outras regras:

- **Código `310000` descartado:** no DATASUS significa "município ignorado – MG" (residência em
  MG, município não informado). Com os dados reais, eram 70 nascimentos e 1.967 óbitos.
- **TMI pelo método direto:** óbitos e nascidos do mesmo ano-calendário, sem correção de
  sub-registro.
- **Código de 7 dígitos reduzido a 6** tirando o último dígito, a mesma ponte da integração.

### 6.2 Educação (`transform_edu.py`)

| Indicador | Definição | Periodicidade |
|---|---|---|
| `IDEB_ANOS_INICIAIS` | IDEB do 1º ao 5º ano, rede pública (escala 0–10) | bienal (anos ímpares) |
| `IDEB_ANOS_FINAIS` | IDEB do 6º ao 9º ano, rede pública (escala 0–10) | bienal (anos ímpares) |
| `TAXA_DISTORCAO` (%) | alunos com 2 ou mais anos de atraso em relação à idade esperada | anual |
| `TAXA_ABANDONO` (%) | alunos que deixaram a escola durante o ano | anual |
| `TAXA_REPROVACAO` (%) | alunos reprovados | anual |
| `MATRICULAS` | matrículas da educação básica | anual |

---

## 7. Integração das fontes: as 6 etapas de qualidade

Implementada em `merge_fontes.py`. Junta `indicadores_saude_mg.parquet` (chave
`cod_municipio_6` + `ano`) e `indicadores_educacao_mg.parquet` (chave `COD_MUNICIPIO` de 7
dígitos + `ano`) em `fato_indicadores.parquet`. As etapas rodam nesta ordem, e cada uma imprime
o que fez.

### 7.1 Etapa 1 — Profiling

**O que faz:** perfila cada fonte **antes de qualquer tratamento**. Por coluna: tipo,
completude (%), número de valores distintos, unicidade (%), mínimo/mediana/máximo das numéricas
e exemplos das textuais. Informa se a chave tem duplicatas e se o código do município foi lido
como número. Salva tudo em `reports/qualidade/perfil_fontes.csv`.

**Por quê:** não se trata um dado que não se conhece. O profiling revela problemas (tipo
errado, nulos, duplicatas) antes que eles se propaguem.

### 7.2 Etapa 2 — Padronização

**O que faz:**

- converte o código do município para **texto**, só com dígitos, com zeros à esquerda;
- remove o sufixo `.0` (de quando o código foi lido como número decimal) **antes** de tirar os
  não-dígitos — senão `3106200.0` viraria `31062000`;
- filtra MG pelo prefixo `31` e descarta o código `310000`/`3100000` (município ignorado);
- converte o ano para inteiro e mantém só 2010–2019.

**Por quê a chave é texto:** como número, o código perde zeros à esquerda e pode virar
`3106200.0`; o join com a outra fonte então **falha em silêncio** (as linhas simplesmente não
casam, sem erro). Nenhum código IBGE começa com zero (as UFs vão de 11 a 53), mas o
preenchimento com zeros fica como defesa.

### 7.3 Etapa 3 — Deduplicação

**O que faz:** garante **uma linha por chave** em cada fonte, **antes** do merge. Havendo
repetição, fica o primeiro valor não-nulo de cada coluna e o script avisa se as repetições
tinham valores diferentes.

**Por quê:**

- **Antes do merge:** uma chave repetida multiplica linhas no join (explosão cartesiana).
- **Nunca soma nem tira média:** chave repetida é registro repetido, não duas medições. Somar
  dobraria nascidos e matrículas; a média inventaria um valor que nenhuma fonte publicou.

### 7.4 Etapa 4 — Merge

**Método: append columns com matching determinístico (exato).**

- **Append columns:** as duas fontes descrevem **atributos diferentes da mesma entidade**
  (município-ano). Integrar é pôr as colunas lado a lado, não empilhar linhas (*append rows*).
- **Matching determinístico, não fuzzy:** existe um identificador oficial, único e estável — o
  código IBGE. O pareamento probabilístico ou fuzzy (como o de Fellegi-Sunter) serve para quando
  **não há** chave comum confiável, como ao cruzar pessoas por nome. Aqui, ele só introduziria
  erro de pareamento (homônimos, grafias diferentes) onde não há ambiguidade. O pareamento
  exato é também **reprodutível e auditável**.

**Ponte 6 → 7 dígitos, sem dígito verificador:** o código de 6 dígitos do DATASUS é o código
IBGE de 7 **sem o último dígito**. Em vez de **calcular** o dígito verificador para estender o
código do DATASUS, o código do INEP é **truncado** para 6 e o casamento é feito por ele.

- Truncar é trivial e não erra; calcular o verificador seria reimplementar um algoritmo.
- O código de 7 dígitos que fica no fato é o **autêntico**, vindo do INEP.
- A ponte é **conferida**: cada código de 6 corresponde a um único de 7, senão o script para.
- O código de 7 também é preenchido nas linhas só de saúde de municípios que aparecem no INEP em
  outros anos.

**Parâmetros do join:** `how="outer"` com `indicator=True` e `validate="1:1"`.

- **Outer, não inner:** o *inner join* descartaria em silêncio o que não casou. O *outer* com
  indicador mostra quanto casou.
- **Coluna `cobertura`** (`ambas` / `so_saude` / `so_educacao`) fica no fato, para a análise
  saber a origem de cada linha.
- **`validate="1:1"`** garante que nenhuma chave casa com mais de uma linha.

### 7.5 Etapa 5 — Survivorship

**O que faz:** define, campo a campo, qual fonte vale quando mais de uma fornece o mesmo dado.
Duas estratégias, num registro configurável no topo do script:

- **`source_priority`:** vale a fonte mais confiável que estiver preenchida. Ordem de confiança
  para atributos de município: **IBGE > INEP > DATASUS** (o IBGE é o dono do cadastro de
  municípios).
- **`most_complete`:** as fontes são ordenadas pela completude do campo, com empate decidido
  pela ordem de confiança.

Para cada campo, o script conta os **conflitos reais** (as duas fontes preenchidas e diferentes)
e de qual fonte veio cada valor.

**Situação atual:** saúde e educação são **complementares** — nenhum campo além da chave aparece
nas duas —, então não há conflito, e o script diz isso explicitamente, sem simular nenhum. As
regras passam a valer se o IBGE entrar como terceira fonte.

**Cuidado de implementação:** ao resolver um campo, só são removidos os nomes **exatos**
`<campo>_datasus` e `<campo>_inep`. Remover por prefixo faria `cod_municipio` apagar também
`cod_municipio_6`, a chave.

### 7.6 Etapa 6 — Validação

**O que faz:** testa invariantes que, se quebrarem, indicam **erro de merge**, não do dado. Se
alguma falha, o fato **não é salvo** e as violações vão para
`reports/qualidade/violacoes_validacao.csv`.

| Invariante | Regra | O que pega |
|---|---|---|
| (a) Municípios distintos | entre 835 e 853 (até 2% a menos, nunca a mais) | acima de 853: UF vazada ou código inválido; muito abaixo: join falhando em silêncio |
| (b) Chave única | zero chaves `cod_municipio_6` + `ano` duplicadas | deduplicação falhou |
| (c) Sem explosão | nº de linhas ≤ 1,3 × a maior fonte | explosão cartesiana |
| (d) Faixas plausíveis | IDEB em [0, 10]; taxas e proporções em [0, 100]; TMI em [0, 1000]; contagens ≥ 0 | valores impossíveis |

**Por que a TMI vai até 1000 e não 100:** em município minúsculo, 1 óbito em 5 nascidos dá 200
por mil — aritmética correta. O script só emite uma **nota informativa** (não falha) com
quantos município-ano têm menos de 100 nascidos: é instabilidade de número pequeno, tratada na
análise (ver [seção 8.1](#81-unidade-de-análise-um-ponto-por-município)).

### 7.7 Validação com problemas plantados

A integração foi testada com dados sintéticos que plantam, de propósito, um problema para cada
etapa:

| Problema plantado | Etapa que pegou |
|---|---|
| Código do município salvo como número / `"310000.0"` | 1 (avisa) e 2 (corrige) |
| Município de outra UF (Rio de Janeiro) no arquivo de MG | 2 (prefixo 31) |
| Chaves duplicadas, com valores divergentes | 3 |
| IDEB = 12,5 | 6 (faixa 0–10; fato não salvo) |
| Coluna esperada ausente | carregamento (erro listando as colunas) |
| Fatos corrompidos: município a mais, municípios perdidos, chave duplicada, explosão | 6 (invariantes a, b, c) |

### 7.8 Resultado com os dados reais

- **8.530 linhas** (853 municípios × 10 anos), **100% de cobertura** (todas as linhas em
  `ambas`), todas as invariantes aprovadas.
- **2.603.425 nascidos vivos** e **30.455 óbitos infantis** no período (TMI de 11,7 por mil).
- **Caso `310000`:** na primeira execução, a invariante (a) barrou o resultado com **854
  municípios**. A investigação mostrou que `310000` é o código do DATASUS para "município
  ignorado" — passava no filtro de MG, mas não é um município. É o exemplo de uma validação
  pegando um problema real que teria criado um município falso.
- **4.506 dos 8.530 município-ano têm menos de 100 nascidos** (11 deles com TMI acima de 100),
  o que motivou a consolidação do período na análise.

---

## 8. Análise estatística

Implementada em `correlacoes.py`; o BI usa as mesmas funções, então os números do texto e do
painel são sempre iguais.

### 8.1 Unidade de análise: um ponto por município

**O que é feito:** os 10 anos de cada município viram um único valor por indicador
(`municipio_periodo.parquet`, 853 linhas).

| Indicador | Consolidação |
|---|---|
| TMI | Σ óbitos infantis (2010–2019) ÷ Σ nascidos vivos (2010–2019) × 1000 |
| Proporções de saúde | média ponderada pelos nascidos: Σ(proporção × nascidos) ÷ Σ nascidos |
| IDEB e taxas do INEP | média simples dos anos disponíveis |

**Por quê:**

- **Independência das observações.** Os testes assumem que cada observação traz informação
  nova. Nas 8.530 linhas, o mesmo município apareceria 10 vezes — Belo Horizonte em 2010 é
  muito parecido com Belo Horizonte em 2011. O teste acharia 8.530 informações independentes
  quando há 853, e daria significância artificialmente alta.
- **Menos ruído nos municípios pequenos.** Com 30 nascidos por ano, 1 óbito a mais faz a TMI
  saltar de 0 para 33 por mil. Somando a década, são 300 nascidos e a taxa fica estável.
- **Somar antes de dividir (TMI) e ponderar (proporções):** a média simples das taxas anuais
  daria o mesmo peso a um ano com 3 nascidos e a um com 300. O IDEB e as taxas do INEP já são
  índices calculados sobre muitos alunos, então a média simples basta.

### 8.2 Dados completos por combinação

**O que é feito:** em cada combinação entram só os municípios com os dois indicadores
preenchidos. Mínimo de 30 municípios para calcular.

**Por quê:** não dá para correlacionar sem um dos valores, e imputar inventaria um dado que
ninguém mediu. Por isso o n é 851 nas combinações com IDEB: dois municípios nunca tiveram o IDEB
de anos iniciais divulgado (o INEP não divulga quando a participação na prova é baixa). Abaixo
de 30 observações a correlação é instável demais.

### 8.3 Correlação de Spearman (ρ)

**O que é:** um número entre −1 e +1 que indica se dois indicadores **sobem juntos**
(positivo), se **um sobe enquanto o outro desce** (negativo) ou se **não têm relação** (perto de
zero).

**Como funciona:** cada variável é convertida em **posições (ranks)** — o município com o menor
valor fica em 1º, o seguinte em 2º, até o 853º; empates recebem a posição média. ρ é a
correlação de Pearson calculada sobre essas posições. Sem empates, equivale a:

```
ρ = 1 − 6·Σd² / [n·(n² − 1)]        d = diferença entre as duas posições de cada município
```

**Por que Spearman, e não Pearson:**

- **Relações não lineares:** Pearson mede só relação em linha reta; Spearman mede qualquer
  relação monotônica (que sempre sobe ou sempre desce), mesmo curva. Relações sociais raramente
  são retas.
- **Valores extremos:** um único município com TMI de 200 por mil (possível com 5 nascidos) pode
  puxar o Pearson sozinho. No Spearman ele é só "o último da fila".
- **Dados assimétricos:** os indicadores não têm distribuição normal (matrículas vão de cerca de
  100 a 580 mil). Spearman não supõe nenhuma distribuição.

### 8.4 p-valor

**O que é:** a probabilidade de encontrar uma correlação tão forte quanto a observada **se não
houvesse relação nenhuma** (se fosse só acaso). Calculado pela estatística t:

```
t = ρ · √[(n − 2) / (1 − ρ²)]       com n − 2 graus de liberdade
```

**Como ler:** p < 0,001 quer dizer que, sem relação real, uma correlação desse tamanho
apareceria por acaso menos de 1 vez em mil.

**O que ele não diz:** não diz o **tamanho** da relação (isso é o ρ) — com 853 municípios, até
correlações fracas dão p pequeno — e não diz que a relação é **causal**. Por isso ρ e p são
sempre apresentados juntos.

### 8.5 Intervalo de confiança de 95% (IC 95%)

**O que é:** a faixa de valores plausíveis para a correlação verdadeira. O ρ calculado é uma
estimativa: com pequenas variações nos dados, ele mudaria um pouco. Se o estudo fosse repetido
muitas vezes, 95% dos intervalos calculados assim conteriam o valor verdadeiro.

**Como é calculado (transformação z de Fisher):**

```
1. z  = arctanh(ρ)
2. EP = √[1,06 / (n − 3)]            erro-padrão para Spearman (Fieller, Hartley e Pearson, 1957)
3. intervalo em z: z ± 1,96 · EP
4. volta para a escala de ρ: tanh(limite inferior) a tanh(limite superior)
```

**Exemplo** (mãe adolescente × abandono, ρ = 0,49, n = 853): z = 0,536; EP = √(1,06/850) =
0,0353; z ± 1,96·EP = 0,467 a 0,605; tanh → **0,44 a 0,54**, o intervalo exibido no BI.

**Por quê:**

- **Mostra a precisão:** um IC estreito (0,44 a 0,54) indica estimativa precisa; um largo
  (−0,10 a 0,60) indica que se sabe pouco.
- **Mostra a significância de forma visual:** se o intervalo **não cruza o zero**, a
  correlação é significativa.
- **Permite comparar combinações:** intervalos que não se sobrepõem indicam diferença real.
- **Por que Fisher:** a correlação é limitada a −1 e +1, então perto desses limites o erro não é
  simétrico. A transformação "estica" a escala para que o erro fique simétrico; o intervalo é
  calculado nessa escala e convertido de volta. O fator 1,06 é a correção específica para
  Spearman.

### 8.6 Correção de Holm (comparações múltiplas)

**O problema:** com α = 0,05, cada teste tem 5% de chance de falso positivo. Com 5 testes, a
chance de **pelo menos um** falso positivo sobe para cerca de 23% (1 − 0,95⁵).

**O que faz:** torna o critério mais exigente para que a chance de **qualquer** falso positivo
entre os 5 testes continue em 5% (controle do erro familiar).

```
1. ordena os 5 p-valores do menor para o maior
2. multiplica o 1º por 5, o 2º por 4, o 3º por 3, o 4º por 2, o 5º por 1
3. garante que cada valor ajustado não seja menor que o anterior; limita a 1
4. significativa se o p ajustado < 0,05
```

**Por que Holm, e não Bonferroni:** o Bonferroni multiplica todos por 5; controla o mesmo erro,
mas é mais conservador e perde correlações reais. O Holm tem mais poder com a mesma garantia.

**Por que as combinações foram escolhidas antes:** se os 48 pares possíveis (8 indicadores de
saúde × 6 de educação) fossem testados e só os significativos apresentados, a correção seria
inútil — os resultados estariam sendo escolhidos depois de vistos.

### 8.7 Força da correlação (faixas de Cohen)

| \|ρ\| | Classificação |
|---|---|
| < 0,1 | desprezível |
| 0,1 a 0,3 | fraca |
| 0,3 a 0,5 | moderada |
| ≥ 0,5 | forte |

**Por quê:** traduz o número para linguagem comum com uma convenção reconhecida (Cohen, 1988) e
evita superinterpretação: "significativa" não quer dizer "forte". O campo "sentido confere"
compara o sinal de ρ com o esperado pela hipótese.

### 8.8 Análise de sensibilidade por porte

**O que é feito:** tudo é refeito só com municípios de **100 ou mais nascidos vivos por ano**
(em média).

**Por quê:** verifica se o resultado depende dos municípios pequenos, onde as taxas oscilam por
acaso. Se o ρ mantém o sinal e a magnitude, a conclusão é **robusta ao porte**.

### 8.9 Correlação ano a ano

**O que é feito:** a mesma correlação, calculada separadamente em cada ano (as combinações com
IDEB, só nos anos ímpares).

**Por quê:** verifica se a relação é **estável no tempo**. Os valores anuais tendem a ser
menores que os do período, porque cada ano tem mais ruído e o ruído "dilui" a correlação. O
importante é o **sinal se manter** ao longo dos anos.

### 8.10 Linha de tendência (medianas por décimo)

**O que é feito:** os municípios são divididos em 10 grupos de igual tamanho pelo indicador de
saúde, e a linha liga a **mediana** dos dois eixos em cada grupo.

**Por quê:** com 853 pontos, a nuvem é difícil de ler; a linha mostra a tendência sem ajustar um
modelo. A mediana resiste a extremos, pelo mesmo motivo de usar Spearman. É só descritiva e não
entra nos testes.

### 8.11 Classificação dos municípios: quadrantes e faixas

**Quadrantes (por combinação).** Cada município é comparado com a **mediana** dos municípios do
recorte em cada indicador do par, respeitando o sentido de cada um (`DIRECAO` em
`correlacoes.py`: TMI, baixo peso, mãe adolescente, baixa escolaridade, distorção, abandono e
reprovação — maior é pior; pré-natal e IDEB — maior é melhor):

| Quadrante | Regra |
|---|---|
| **Crítico** | pior que a mediana na saúde **e** na educação |
| **Moderado – saúde** | pior só no indicador de saúde |
| **Moderado – educação** | pior só no indicador de educação |
| **Não crítico** | melhor ou igual à mediana nos dois |

Para cada município conta-se ainda em quantas das 5 combinações ele é **Crítico** (0 a 5), o que
aponta onde saúde e educação estão piores ao mesmo tempo, em vários aspectos.

**Faixas (por indicador).** Cada indicador é dividido em **quartis** orientados pela gravidade:
**Adequada** (melhor 25%), **Atenção**, **Alerta** e **Grave** (pior 25%). A classificação usa a
posição percentual do município, de modo que valores empatados (ex.: muitos abandonos iguais a
zero) caem na mesma faixa.

**Por que mediana e quartis:** são cortes **robustos** a valores extremos (coerentes com o uso de
Spearman) e dividem os municípios em grupos de tamanho conhecido. A classificação é **relativa**:
indica a posição do município entre os de MG, e não o cumprimento de uma meta absoluta (como uma
meta de TMI). É **descritiva** — não é um teste estatístico e não entra na correção de Holm.

**Saída:** `data/processed/classificacao_municipios.csv` e a figura `correlacoes_quadrantes.png`.

### 8.12 Resumo do método

> Consolidamos o período para ter observações independentes e taxas estáveis; usamos Spearman
> por ser robusto a extremos e a relações não lineares; reportamos o IC 95% para mostrar a
> precisão e o tamanho do efeito, não só a significância; corrigimos por Holm porque fizemos 5
> testes; e confirmamos a robustez com a análise por porte e ano a ano.

---

## 9. As 5 combinações analisadas

Definidas **antes** de olhar os dados, cada uma com uma hipótese teórica. Configuráveis em
`PARES`, no topo de `correlacoes.py`.

| # | Saúde | Educação | Sentido esperado | Hipótese |
|---|---|---|---|---|
| 1 | Mãe adolescente (%) | Abandono escolar (%) | positivo | a gravidez na adolescência interrompe a trajetória escolar, e a evasão expõe à gravidez precoce |
| 2 | Mãe com < 8 anos de estudo (%) | Distorção idade-série (%) | positivo | a escolaridade se transmite entre gerações; também testa se SINASC e INEP "contam a mesma história" |
| 3 | Pré-natal com 7+ consultas (%) | IDEB anos iniciais | positivo | atenção básica e anos iniciais do fundamental são responsabilidade do município: quem organiza bem um serviço tende a organizar bem o outro |
| 4 | TMI (por mil) | IDEB anos iniciais | negativo | os indicadores-síntese de cada área andam em sentidos opostos |
| 5 | Baixo peso ao nascer (%) | Reprovação (%) | positivo | condições ao nascer afetam o desenvolvimento escolar; hipótese mais fraca no nível municipal (coortes não coincidem no tempo), usada como **contraste** |

---

## 10. Resultados

### 10.1 Período consolidado (todos os municípios)

| # | Combinação | n | ρ | IC 95% | p (Holm) | Força | Sentido |
|---|---|---|---|---|---|---|---|
| 1 | Mãe adolescente × Abandono | 853 | **0,49** | 0,44 a 0,54 | < 0,001 | moderada | confere |
| 2 | Baixa escolaridade materna × Distorção | 853 | **0,46** | 0,40 a 0,51 | < 0,001 | moderada | confere |
| 3 | Pré-natal × IDEB anos iniciais | 851 | **0,31** | 0,25 a 0,37 | < 0,001 | moderada | confere |
| 4 | TMI × IDEB anos iniciais | 851 | **−0,19** | −0,26 a −0,12 | < 0,001 | fraca | confere |
| 5 | Baixo peso × Reprovação | 853 | ≈ 0 | inclui o zero | não significativa | desprezível | — |

**4 de 5 combinações são significativas após a correção de Holm, todas no sentido da
hipótese.** Os valores exatos estão em `data/processed/correlacoes_periodo.csv`.

### 10.2 Robustez

- **Por porte (≥ 100 nascidos/ano):** os coeficientes mantiveram o sinal e magnitude semelhante;
  a dispersão diminui porque saem os municípios com taxas instáveis. Valores no cenário
  `porte>=100` de `correlacoes_periodo.csv`.
- **Ano a ano:** o sinal se mantém em todos os anos, com valores anuais menores que os do
  período (mais ruído por ano). TMI × IDEB é a mais fraca ano a ano, quase nula em alguns anos,
  porque a TMI de um único ano é muito instável nos municípios pequenos; somando a década, a
  relação aparece. Valores em `correlacoes_por_ano.csv`.

### 10.3 Conclusões

1. **As associações mais fortes passam pela mãe.** Gravidez na adolescência × abandono (0,49) e
   escolaridade materna × distorção (0,46) sugerem que a trajetória educacional das mulheres
   jovens é o elo mais forte entre as duas áreas.
2. **A gestão dos serviços municipais aparece nos dois lados.** Pré-natal × IDEB anos iniciais
   (0,31) liga dois serviços municipais, compatível com a ideia de capacidade de gestão local.
3. **Os indicadores-síntese se relacionam pouco.** TMI × IDEB (−0,19) vai no sentido esperado,
   mas é fraca e só aparece com o período consolidado: a escolha do indicador e da agregação muda
   o que se consegue enxergar.
4. **Nem toda relação plausível aparece.** Baixo peso × reprovação deu nulo, como antecipado; isso
   mostra que o método não encontra correlação em tudo e dá credibilidade às demais.
5. **Os resultados são robustos** ao porte do município e estáveis ao longo de 2010–2019.

**Implicação:** saúde e educação não deveriam ser planejadas isoladamente no município — a
gravidez na adolescência, por exemplo, é um problema das duas áreas.

**Alcance:** são **associações no nível municipal**, não efeitos causais (ver
[seção 13](#13-limitações)).

---

## 11. Visualização: figuras e BI

### 11.1 Figuras estáticas (para o texto)

| Arquivo | O que mostra |
|---|---|
| `integracao_pipeline.png` | as duas fontes, as 6 etapas e o fato resultante |
| `integracao_ponte_codigo.png` | a ponte 6 → 7 dígitos (exemplo: Belo Horizonte, `3106200` → `310620`) |
| `integracao_completude.png` | completude por indicador e ano (IDEB vazio nos anos pares, por desenho) |
| `integracao_funil_tmi.png` | TMI × nascidos (funnel plot): a dispersão explode abaixo de ~100 nascidos |
| `correlacoes_forest.png` | ρ e IC 95% das 5 combinações, nos dois cenários de porte |
| `correlacoes_dispersao.png` | dispersão de cada combinação, com a tendência por décimos |
| `correlacoes_por_ano.png` | ρ ano a ano de cada combinação |
| `correlacoes_quadrantes.png` | municípios coloridos por quadrante em cada combinação, com as medianas |

O **funnel plot** marca, em torno da TMI estadual, os limites de variação esperada por acaso
(binomiais de 95% e 99,8%). Pontos fora dos limites nos municípios pequenos são esperados e
não indicam erro — é a justificativa visual para consolidar o período.

### 11.2 BI (`streamlit run app_bi.py`)

- **Filtros no topo, que valem para todo o painel:** recorte temporal (período consolidado ou um
  ano), porte mínimo (nascidos por ano) e município em destaque.
- **Indicadores do recorte:** municípios, nascidos vivos, TMI e IDEB mediano.
- **Aba Resumo:** forest plot das 5 combinações e tabela com ρ, IC, p de Holm, força e sentido.
- **Uma aba por combinação:** hipótese, ρ, IC, p ajustado e n; dispersão com a tendência e o
  município destacado; ρ ano a ano; tabela dos dados com download em CSV.
- **Classificação em quadrantes** em cada aba de combinação: contagem por quadrante e dispersão
  colorida por quadrante (cor + símbolo), com as medianas tracejadas; lista de municípios filtrável.
- **Aba Classificação:** quantos municípios são críticos em 0 a 5 combinações, lista dos mais
  críticos e faixas (Adequada, Atenção, Alerta, Grave) de qualquer indicador, com download.
- **Aba Metodologia:** resumo do método, da classificação e das limitações.
- **Tema claro e escuro de alto contraste** (`.streamlit/config.toml`; ⋮ → Settings → Theme):
  texto com contraste acima de 17:1, cores de marca acima de 3:1 sobre o fundo e cores dos
  quadrantes validadas para daltonismo, com símbolo próprio em cada quadrante (losango, triângulo,
  quadrado, círculo) como segunda codificação.

---

## 12. Decisões de escopo

### 12.1 Sem controle socioeconômico

Por decisão com o orientador, a análise não inclui uma variável de controle socioeconômico (como
o IDHM). Consequência: as correlações são **associações**, e parte delas pode refletir o nível de
desenvolvimento do município, que afeta saúde e educação ao mesmo tempo.

### 12.2 CNES fora da análise

O CNES foi extraído (`data/raw/cnes_mg.parquet`) e fica preservado na camada bronze, mas não é
usado em nenhum indicador. Justificativa:

1. **Mede oferta, e a pergunta é sobre resultados.** As demais variáveis medem desfechos na
   população (mortalidade, condições do nascimento, desempenho escolar). O CNES conta
   estabelecimentos — um insumo. Misturar os dois mudaria a pergunta.
2. **Exigiria a população como denominador.** O número bruto de estabelecimentos acompanha o
   tamanho do município. Para comparar, seria preciso uma taxa por habitante, que depende da
   população do IBGE — fora do escopo. Sem isso, qualquer correlação refletiria o porte.
3. **Seria a variável mais confundida.** Sem controle socioeconômico, a oferta de serviços é das
   variáveis mais ligadas ao desenvolvimento do município.
4. **O acesso já é medido por um indicador melhor.** O pré-natal adequado (SINASC) mede o **uso
   efetivo** da atenção básica; ter uma unidade de saúde não garante atendimento.
5. **Qualidade e formato do cadastro.** É mantido pelos gestores e pode conter estabelecimentos
   desativados; o projeto extraiu só dezembro de cada ano, e um indicador anual confiável exigiria
   uma validação própria.

### 12.3 População do IBGE

Não incorporada. Não faz falta hoje: os indicadores de saúde usam os nascidos vivos como
denominador, e a ponte entre os códigos é feita pelo INEP.

### 12.4 Star schema

Não implementado. O fato é uma **tabela larga** (município + ano como chave, 14 indicadores em
colunas), sem tabelas de dimensão separadas. Justificativa: com só duas dimensões (município e
ano), a tabela larga atende a análise e o BI diretamente; o star schema (Kimball e Ross, 2013)
compensa quando há muitas dimensões e várias tabelas fato. Se necessário, a modelagem seria:
`fato_indicadores` (chaves + medidas), `dim_municipio` (códigos de 6 e 7 dígitos e nome) e
`dim_tempo` (ano, triênio, se o ano tem IDEB).

### 12.5 Orquestração

Os scripts são executados em sequência ([seção 4.2](#42-ordem-de-execução)). Uma ferramenta como
o Apache Airflow não foi adotada: ela resolve execuções agendadas e recorrentes, com novas
tentativas e monitoramento, enquanto este pipeline roda sob demanda sobre dados históricos
(2010–2019) que não mudam — e o Airflow não roda nativamente no Windows (exige WSL ou Docker).

---

## 13. Limitações

- **Associação, não causalidade:** sem controle socioeconômico, as correlações podem refletir
  fatores comuns às duas áreas.
- **Falácia ecológica** (Robinson, 1950): a unidade é o município; nada se conclui sobre
  indivíduos (não dá para dizer que uma mãe adolescente específica abandona a escola).
- **Correlações moderadas:** indicam tendência, não determinismo; há muitos municípios fora do
  padrão.
- **Autocorrelação espacial:** municípios vizinhos se parecem, o que torna os p-valores otimistas.
- **Coortes diferentes:** os nascidos de um ano não são os alunos avaliados no mesmo ano; a
  análise não usa defasagem temporal.
- **TMI pelo método direto,** sem correção de sub-registro de óbitos e nascimentos.
- **IDEB bienal:** as combinações com IDEB usam só 5 dos 10 anos.
- **Corte de baixa escolaridade materna** (menos de 8 anos de estudo) é uma escolha do projeto.

---

## 14. Trabalhos futuros

1. Incluir controle socioeconômico (ex.: IDHM) e calcular correlações parciais.
2. Incorporar a população do IBGE e indicadores de oferta (CNES) como taxas por habitante.
3. Usar defasagem temporal entre as coortes de nascimento e de avaliação escolar.
4. Testar e modelar a autocorrelação espacial (ex.: I de Moran).
5. Modelar a camada gold em star schema e carregar num banco relacional (PostgreSQL).
6. Criar um orquestrador (`pipeline.py`, ou Prefect/Airflow) para rodar o pipeline com um comando.

---

## 15. Referências

- COHEN, J. *Statistical Power Analysis for the Behavioral Sciences*. 2. ed. Hillsdale: Lawrence
  Erlbaum, 1988.
- FELLEGI, I. P.; SUNTER, A. B. A theory for record linkage. *Journal of the American
  Statistical Association*, v. 64, n. 328, p. 1183–1210, 1969.
- FIELLER, E. C.; HARTLEY, H. O.; PEARSON, E. S. Tests for rank correlation coefficients. I.
  *Biometrika*, v. 44, n. 3/4, p. 470–481, 1957.
- FISHER, R. A. Frequency distribution of the values of the correlation coefficient in samples
  from an indefinitely large population. *Biometrika*, v. 10, n. 4, p. 507–521, 1915.
- HOLM, S. A simple sequentially rejective multiple test procedure. *Scandinavian Journal of
  Statistics*, v. 6, n. 2, p. 65–70, 1979.
- KIMBALL, R.; ROSS, M. *The Data Warehouse Toolkit*. 3. ed. Indianapolis: Wiley, 2013.
- ROBINSON, W. S. Ecological correlations and the behavior of individuals. *American
  Sociological Review*, v. 15, n. 3, p. 351–357, 1950.
- SPEARMAN, C. The proof and measurement of association between two things. *The American
  Journal of Psychology*, v. 15, n. 1, p. 72–101, 1904.
- SPIEGELHALTER, D. J. Funnel plots for comparing institutional performance. *Statistics in
  Medicine*, v. 24, n. 8, p. 1185–1202, 2005.
