"""
Tratamento dos dados de EDUCAÇÃO: seleção de colunas + limpeza -> data/interim,
e cálculo dos indicadores no grão município-ano -> data/processed.

Mesmas regras aprendidas na parte de saúde, aplicadas aqui:
  1. NUNCA confia no filtro de UF da fonte — filtra MG pelo prefixo "31" do
     código de município (todo código IBGE de MG começa com 31), logo após
     normalizar o código como texto e ANTES de qualquer contagem.
  2. Código de município do INEP tem 7 dígitos (o do DATASUS tem 6) e é
     sempre TEXTO — nunca calculamos dígito verificador.
  3. Lê só as colunas necessárias do parquet; nunca transpõe DataFrame grande.
  4. Layout muda de edição para edição do INEP: normaliza nomes de coluna
     para MAIÚSCULA (sem acento) e funde colunas duplicadas com
     combine_first, coluna a coluna, sem transpor.
  5. Códigos de "ignorado"/"não aplicável" viram NaN antes de qualquer média
     ou proporção. O sentinela varia por campo — ver IGNORADO_EDU_PADRAO em
     config.py e conferir contra os arquivos reais.
  6. Depois de filtrar/agregar, sempre imprime linhas por ano para validação.

Os nomes de coluna vêm do cabeçalho das planilhas do INEP (ver
extract_edu._nomes_colunas) e mudam entre edições: em algumas há nomes
técnicos (TDI_FUN, FUN_CAT_0), em outras rótulos compostos ("Taxa de
Abandono | Ensino Fundamental de 8 e 9 anos | Total"). Por isso as colunas de
valor são achadas por regex sobre o nome normalizado (_fundir_por_padrao),
conferida contra os arquivos 2010–2019. Preferimos falhar com um erro claro
(KeyError listando as colunas disponíveis) a seguir em frente com a coluna
errada.
"""
import re
import unicodedata

import pandas as pd

from config import (
    RAW, INTERIM, PROCESSED, ANOS,
    COLS_CANDIDATAS_COD_MUNICIPIO, COLS_CANDIDATAS_NOME_MUNICIPIO,
    COLS_CANDIDATAS_LOCALIZACAO, COLS_CANDIDATAS_REDE,
    LOCALIZACAO_EDU, REDE_EDU, REDE_IDEB,
    IGNORADO_EDU_PADRAO,
)

COD_MUNICIPIO_TAMANHO = 7  # INEP usa 7 dígitos — não confundir com os 6 do DATASUS


def _sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _chave_comparacao(s):
    """Normaliza um nome de coluna para comparação: maiúsculo, sem acento/espaço/underscore."""
    return _sem_acento(str(s)).upper().replace(" ", "").replace("_", "").strip()


def _normalizar_nomes_colunas(df):
    """Maiúsculas e sem acento — o layout do INEP muda de caixa/acentuação entre edições."""
    df = df.copy()
    df.columns = [_sem_acento(str(c)).upper().strip() for c in df.columns]
    return df


def _fundir_colunas_duplicadas(df):
    """
    Após normalizar nomes, colunas que só diferiam por acento/caixa viram
    duplicadas (mesmo nome repetido). Funde com combine_first coluna a
    coluna — nunca transpõe (estouraria RAM em base grande).
    """
    if not df.columns.duplicated().any():
        return df
    resultado = {}
    for nome in pd.unique(df.columns):
        mesmas = df.loc[:, df.columns == nome]
        col = mesmas.iloc[:, 0]
        for i in range(1, mesmas.shape[1]):
            col = col.combine_first(mesmas.iloc[:, i])
        resultado[nome] = col
    return pd.DataFrame(resultado)


def _fundir_por_candidatos(df, candidatos, nome_canonico, obrigatoria=True):
    """
    Acha TODAS as colunas cujo nome bate com a lista de candidatos (comparação
    tolerante a espaço/underscore/acento) — pode haver mais de uma quando o
    DataFrame junta arquivos de anos diferentes e cada edição do INEP usou um
    nome distinto para o mesmo campo (ex.:
    "CO_MUNICIPIO" em 2017, "Código do Município" em 2019) — e funde todas
    com combine_first numa única coluna canônica, coluna a coluna, sem
    transpor. Sem isso, pegar só a "primeira" coluna que bate (como faz
    _achar_coluna) deixaria os anos com o nome "errado" vazios e eles
    seriam descartados sem aviso no filtro de MG.
    """
    candidatos_chave = {_chave_comparacao(c) for c in candidatos}
    encontradas = [c for c in df.columns if _chave_comparacao(c) in candidatos_chave]

    if not encontradas:
        if obrigatoria:
            raise KeyError(
                f"Nenhuma coluna encontrada entre os candidatos {candidatos}. "
                f"Colunas disponíveis: {list(df.columns)}. "
                "Ajuste a lista de candidatos conforme o layout real do arquivo do INEP."
            )
        return df, None

    df = df.copy()
    coluna_fundida = df[encontradas[0]]
    for outra in encontradas[1:]:
        coluna_fundida = coluna_fundida.combine_first(df[outra])

    df = df.drop(columns=[c for c in encontradas if c != nome_canonico])
    df[nome_canonico] = coluna_fundida
    return df, nome_canonico


def _fundir_por_padrao(df, padrao, nome_canonico, rotulo):
    """
    Como _fundir_por_candidatos, mas casa o nome normalizado da coluna
    (_chave_comparacao: maiúsculo, sem acento/espaço/underscore) com uma
    regex — necessário quando o rótulo traz o ano ou muda de redação a cada
    edição. Confere que cada ano tem exatamente UMA coluna preenchida casando,
    para não fundir por engano, por exemplo, o total do Fundamental com o do
    Médio.
    """
    regex = re.compile(padrao)
    encontradas = [c for c in df.columns if regex.search(_chave_comparacao(c))]
    if not encontradas:
        raise KeyError(f"[{rotulo}] nenhuma coluna casa com {padrao!r}. "
                       f"Colunas disponíveis: {list(df.columns)}")

    for ano, grupo in df.groupby("ano"):
        preenchidas = [c for c in encontradas if grupo[c].notna().any()]
        if len(preenchidas) != 1:
            raise KeyError(f"[{rotulo}] {ano}: esperava 1 coluna casando com {padrao!r}, "
                           f"achei {preenchidas}")

    df = df.copy()
    coluna_fundida = df[encontradas[0]]
    for outra in encontradas[1:]:
        coluna_fundida = coluna_fundida.combine_first(df[outra])
    df = df.drop(columns=encontradas)
    df[nome_canonico] = coluna_fundida
    return df, nome_canonico


def _filtrar_categoria(df, candidatos, valor, rotulo, descricao):
    """
    Mantém só as linhas em que a coluna de categoria (localização ou rede)
    é igual a `valor` (comparação sem acento/caixa).
    """
    df, col = _fundir_por_candidatos(df, candidatos, f"_{descricao.upper()}")
    alvo = _chave_comparacao(valor)
    mantidas = df[df[col].map(_chave_comparacao) == alvo]
    if mantidas.empty:
        raise ValueError(f"[{rotulo}] nenhuma linha com {descricao} = {valor!r}. "
                         f"Valores existentes: {sorted(df[col].dropna().unique())}")
    return mantidas.drop(columns=[col])


def _padronizar_cod_municipio(df, col_cod):
    df = df.copy()
    df[col_cod] = (df[col_cod].astype(str).str.strip()
                   .str.replace(r"\.0$", "", regex=True)  # Excel às vezes lê código como float
                   .str.zfill(COD_MUNICIPIO_TAMANHO))
    return df


def _filtrar_mg(df, col_cod):
    """
    REGRA 1: nunca confia no filtro de UF da fonte, mesmo que o arquivo diga
    "municípios". Filtra pelo prefixo "31" do código do município — todo
    código IBGE de MG começa com 31 — logo após normalizar o código, antes
    de qualquer contagem.
    """
    return df[df[col_cod].str.startswith("31")].copy()


def _limpar_sentinelas(df, colunas, sentinelas=IGNORADO_EDU_PADRAO):
    """Substitui códigos de 'ignorado'/'não aplicável' por NaN (regra 5)."""
    df = df.copy()
    for col in colunas:
        if col in df.columns:
            df[col] = df[col].astype("string").str.strip().replace(sentinelas, pd.NA)
    return df


def _para_numerico(serie):
    """Números do INEP às vezes vêm com vírgula decimal em vez de ponto."""
    return pd.to_numeric(serie.astype("string").str.replace(",", ".", regex=False), errors="coerce")


def _imprimir_linhas_por_ano(df, rotulo, col_ano="ano"):
    print(f"[{rotulo}] linhas por ano:")
    print(df.groupby(col_ano).size().to_string())


def _agregar_municipio_ano(df, col_valor, como="mean"):
    """
    Leva para o grão município-ano. Depois do filtro Localização/Rede =
    Total (_filtrar_categoria) já deve sobrar uma linha por município-ano;
    se sobrar mais de uma, avisa em vez de agregar em silêncio — média de
    taxas de quebras diferentes não é a taxa do município.
    """
    repetidas = df.duplicated(subset=["COD_MUNICIPIO", "ano"], keep=False)
    if repetidas.any():
        print(f"  AVISO: {repetidas.sum()} linhas com município-ano repetido em "
              f"{col_valor}; agregando com {como}. Exemplos:\n"
              f"{df.loc[repetidas, ['COD_MUNICIPIO', 'ano', col_valor]].head().to_string()}")
    agrupado = df.groupby(["COD_MUNICIPIO", "ano"])[col_valor]
    valor = agrupado.mean() if como == "mean" else agrupado.sum()
    return valor.reset_index()


def _preparar_base(nome_arquivo_raw, rotulo):
    """
    Passos comuns a todas as fontes de educação: ler o parquet cru, normalizar
    cabeçalho, fundir colunas duplicadas, padronizar e filtrar o código de
    município (MG) e deduplicar.
    """
    caminho = RAW / nome_arquivo_raw
    if not caminho.exists():
        print(f"[{rotulo}] {caminho.name} não encontrado — rode extract_edu.py "
              "com os arquivos brutos em data/raw/edu/. Pulando.")
        return None

    df = pd.read_parquet(caminho)
    df = _normalizar_nomes_colunas(df)
    df = _fundir_colunas_duplicadas(df)

    # o DataFrame cru junta vários anos e o nome da coluna de código de
    # município pode mudar entre edições — funde todos os candidatos
    # encontrados em vez de pegar só o primeiro (senão os anos com o nome
    # "errado" ficam vazios e somem no filtro de MG a seguir).
    df, col_cod = _fundir_por_candidatos(df, COLS_CANDIDATAS_COD_MUNICIPIO, "COD_MUNICIPIO")
    df = _padronizar_cod_municipio(df, col_cod)
    df = _filtrar_mg(df, col_cod)
    df = df.rename(columns={"_ANO_ARQUIVO": "ano"})

    df = df.drop_duplicates()
    return df


# ---------------------------------------------------------------------------
# IDEB — anos iniciais e anos finais do ensino fundamental (BIENAL)
# ---------------------------------------------------------------------------

def _tratar_ideb(nome_arquivo_raw, rotulo, nome_saida, nome_coluna_destino):
    df = _preparar_base(nome_arquivo_raw, rotulo)
    if df is None:
        return None

    # o arquivo de divulgação de 2019 é "largo": uma linha por município x
    # rede, com o IDEB de cada edição em VL_OBSERVADO_<ano>. Passa para o
    # formato longo (município-ano) e fica só com os anos do estudo.
    df = _filtrar_categoria(df, COLS_CANDIDATAS_REDE, REDE_IDEB, rotulo, "rede")
    cols_ideb = {c: int(m.group(1)) for c in df.columns
                 if (m := re.fullmatch(r"VL_OBSERVADO_(\d{4})", c))}
    if not cols_ideb:
        raise KeyError(f"[{rotulo}] nenhuma coluna VL_OBSERVADO_<ano> em {list(df.columns)}")

    longo = df[["COD_MUNICIPIO", *cols_ideb]].melt(
        id_vars="COD_MUNICIPIO", var_name="_col", value_name="_valor")
    longo["ano"] = longo["_col"].map(cols_ideb)
    longo = longo[longo["ano"].isin(ANOS)]
    longo = _limpar_sentinelas(longo, ["_valor"])
    longo[nome_coluna_destino] = _para_numerico(longo["_valor"])

    saida = longo[["COD_MUNICIPIO", "ano", nome_coluna_destino]].dropna(subset=[nome_coluna_destino])
    saida = saida.drop_duplicates(subset=["COD_MUNICIPIO", "ano"])

    saida.to_parquet(INTERIM / nome_saida, index=False)
    print(f"[{rotulo}] tratado: {saida.shape[0]:,} linhas | "
          f"municípios distintos: {saida['COD_MUNICIPIO'].nunique()}")
    _imprimir_linhas_por_ano(saida, rotulo)
    return saida


def tratar_ideb_iniciais():
    return _tratar_ideb("ideb_iniciais.parquet", "IDEB anos iniciais",
                         "ideb_iniciais_mg.parquet", "IDEB_ANOS_INICIAIS")


def tratar_ideb_finais():
    return _tratar_ideb("ideb_finais.parquet", "IDEB anos finais",
                         "ideb_finais_mg.parquet", "IDEB_ANOS_FINAIS")


# ---------------------------------------------------------------------------
# Censo Escolar — matrículas, distorção idade-série, taxas de rendimento (ANUAL)
# ---------------------------------------------------------------------------

def tratar_matriculas():
    df = _preparar_base("matriculas.parquet", "Matrículas (Censo Escolar)")
    if df is None:
        return None

    # aba "Educação Básica 1.1" da sinopse: "Número de Matrículas da Educação
    # Básica | Total1-4" (o "1-4" é chamada de nota de rodapé do INEP)
    df, col_mat = _fundir_por_padrao(
        df, r"MATRICULAS.*BASICA\|TOTAL[\d-]*$", "_MATRICULAS_BRUTO", "Matrículas")
    df = _limpar_sentinelas(df, [col_mat])
    df["MATRICULAS"] = _para_numerico(df[col_mat])

    saida = _agregar_municipio_ano(df.dropna(subset=["MATRICULAS"]), "MATRICULAS", como="sum")
    saida.to_parquet(INTERIM / "matriculas_mg.parquet", index=False)
    print(f"[Matrículas] tratado: {saida.shape[0]:,} linhas município-ano")
    _imprimir_linhas_por_ano(saida, "Matrículas")
    return saida


def tratar_distorcao():
    df = _preparar_base("distorcao.parquet", "Distorção idade-série")
    if df is None:
        return None

    df = _filtrar_categoria(df, COLS_CANDIDATAS_LOCALIZACAO, LOCALIZACAO_EDU, "Distorção", "localizacao")
    df = _filtrar_categoria(df, COLS_CANDIDATAS_REDE, REDE_EDU, "Distorção", "rede")
    # total do Ensino Fundamental: rótulo em 2010–2012, TDI_FUN em
    # 2013–2018, FUN_CAT_0 em 2019
    df, col = _fundir_por_padrao(
        df, r"^TDIFUN$|^FUNCAT0$|DISTORCAO.*FUNDAMENTAL.*\|TOTALFUNDAMENTAL$",
        "_DISTORCAO_BRUTO", "Distorção")
    df = _limpar_sentinelas(df, [col])
    df["TAXA_DISTORCAO"] = _para_numerico(df[col])

    saida = _agregar_municipio_ano(df.dropna(subset=["TAXA_DISTORCAO"]), "TAXA_DISTORCAO", como="mean")
    saida.to_parquet(INTERIM / "distorcao_mg.parquet", index=False)
    print(f"[Distorção idade-série] tratado: {saida.shape[0]:,} linhas município-ano")
    _imprimir_linhas_por_ano(saida, "Distorção idade-série")
    return saida


def tratar_rendimento():
    df = _preparar_base("rendimento.parquet", "Taxas de rendimento")
    if df is None:
        return None

    df = _filtrar_categoria(df, COLS_CANDIDATAS_LOCALIZACAO, LOCALIZACAO_EDU, "Rendimento", "localizacao")
    df = _filtrar_categoria(df, COLS_CANDIDATAS_REDE, REDE_EDU, "Rendimento", "rede")
    # total do Ensino Fundamental. Rótulos: "... | Total Abandono Fundamental"
    # (2010), "... | Total Abandono Ens. Fundamental" (2011–2015),
    # "Taxa de Abandono | Ensino Fundamental de 8 e 9 anos | Total" (2016–2019)
    padrao = r"{0}.*(FUNDAMENTALDE8E9ANOS\|TOTAL|\|TOTAL{0}(NO)?(ENS\.)?FUNDAMENTAL)$"
    df, col_aband = _fundir_por_padrao(df, padrao.format("ABANDONO"), "_ABANDONO_BRUTO", "Rendimento")
    df, col_reprov = _fundir_por_padrao(df, padrao.format("REPROVACAO"), "_REPROVACAO_BRUTO", "Rendimento")
    df = _limpar_sentinelas(df, [col_aband, col_reprov])
    df["TAXA_ABANDONO"] = _para_numerico(df[col_aband])
    df["TAXA_REPROVACAO"] = _para_numerico(df[col_reprov])

    aband = _agregar_municipio_ano(df.dropna(subset=["TAXA_ABANDONO"]), "TAXA_ABANDONO", como="mean")
    reprov = _agregar_municipio_ano(df.dropna(subset=["TAXA_REPROVACAO"]), "TAXA_REPROVACAO", como="mean")
    saida = aband.merge(reprov, on=["COD_MUNICIPIO", "ano"], how="outer")

    saida.to_parquet(INTERIM / "rendimento_mg.parquet", index=False)
    print(f"[Taxas de rendimento] tratado: {saida.shape[0]:,} linhas município-ano")
    _imprimir_linhas_por_ano(saida, "Taxas de rendimento")
    return saida


# ---------------------------------------------------------------------------
# Tabela auxiliar código -> nome de município (só para leitura humana na EDA)
# ---------------------------------------------------------------------------

def construir_dim_municipio():
    """
    Monta código -> nome de município a partir da primeira fonte de educação
    disponível, só para facilitar a leitura da EDA (ex.: top/bottom por
    IDEB). Não é a fonte de verdade para outros atributos do município —
    isso continua vindo da tabela do IBGE, como na parte de saúde.
    """
    fontes = ["ideb_iniciais.parquet", "ideb_finais.parquet",
              "matriculas.parquet", "distorcao.parquet", "rendimento.parquet"]
    for nome_arquivo in fontes:
        caminho = RAW / nome_arquivo
        if not caminho.exists():
            continue
        df = pd.read_parquet(caminho)
        df = _normalizar_nomes_colunas(df)
        df = _fundir_colunas_duplicadas(df)

        df, col_cod = _fundir_por_candidatos(df, COLS_CANDIDATAS_COD_MUNICIPIO, "COD_MUNICIPIO", obrigatoria=False)
        df, col_nome = _fundir_por_candidatos(df, COLS_CANDIDATAS_NOME_MUNICIPIO, "NOME_MUNICIPIO", obrigatoria=False)
        if col_cod is None or col_nome is None:
            continue

        df = _padronizar_cod_municipio(df, col_cod)
        df = _filtrar_mg(df, col_cod)
        dim = df[[col_cod, col_nome]].drop_duplicates(subset=col_cod)

        dim.to_parquet(PROCESSED / "dim_municipio_edu_mg.parquet", index=False)
        print(f"[dim_municipio] {dim.shape[0]} municípios (a partir de {nome_arquivo})")
        return dim

    print("[dim_municipio] nenhuma fonte disponível para montar nome dos municípios.")
    return None


# ---------------------------------------------------------------------------
# Grão final: município-ano
# ---------------------------------------------------------------------------

def calcular_indicadores_educacao():
    """
    Junta todos os indicadores de educação no grão município-ano.

    O IDEB só existe em anos ÍMPARES (2011, 2013, 2015, 2017, 2019) — nos
    anos pares as colunas IDEB_ANOS_INICIAIS/FINAIS ficam com NaN de
    propósito (não é falha de join, é a periodicidade real do indicador).
    """
    partes = [
        ("ideb_iniciais_mg.parquet", None),
        ("ideb_finais_mg.parquet", None),
        ("matriculas_mg.parquet", None),
        ("distorcao_mg.parquet", None),
        ("rendimento_mg.parquet", None),
    ]

    base = None
    for arquivo, _ in partes:
        caminho = INTERIM / arquivo
        if not caminho.exists():
            continue
        df = pd.read_parquet(caminho)
        base = df if base is None else base.merge(df, on=["COD_MUNICIPIO", "ano"], how="outer")

    if base is None:
        print("Nenhum indicador de educação disponível — rode as funções tratar_* primeiro.")
        return None

    base = base.sort_values(["COD_MUNICIPIO", "ano"]).reset_index(drop=True)
    base.to_parquet(PROCESSED / "indicadores_educacao_mg.parquet", index=False)

    print(f"\nIndicadores de educação (grão município-ano): {base.shape[0]:,} linhas, "
          f"{base.shape[1]} colunas")
    _imprimir_linhas_por_ano(base, "indicadores_educacao_mg")
    return base


def main():
    tratar_ideb_iniciais()
    tratar_ideb_finais()
    tratar_matriculas()
    tratar_distorcao()
    tratar_rendimento()
    construir_dim_municipio()
    calcular_indicadores_educacao()
    print("\nTratamento concluído. Arquivos em:", INTERIM, "e", PROCESSED)


if __name__ == "__main__":
    main()
