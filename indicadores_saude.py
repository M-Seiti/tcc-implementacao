import pandas as pd
import pyarrow.parquet as pq

from config import INTERIM, PROCESSED, ANOS

COLS_SINASC_USADAS = ["CODMUNRES", "ano", "PESO", "IDADEMAE", "ESCMAE", "CONSULTAS", "PARTO"]
COLS_SIM_USADAS = ["CODMUNRES", "ano", "obito_infantil"]
ESCOLARIDADE_BAIXA = {"1", "2", "3"}  # nenhuma, 1–3 e 4–7 anos: menos de 8 anos de estudo


# Lê um parquet do interim e falha se faltar alguma coluna esperada.
def _ler(nome, colunas):
    caminho = INTERIM / nome
    if not caminho.exists():
        raise FileNotFoundError(f"{caminho} não encontrado — rode `python transform.py` antes.")
    disponiveis = pq.ParquetFile(caminho).schema_arrow.names
    faltando = [c for c in colunas if c not in disponiveis]
    if faltando:
        raise KeyError(f"{nome}: colunas ausentes {faltando}. Disponíveis: {disponiveis}")
    return pd.read_parquet(caminho, columns=colunas)


# Código de município como texto de 6 dígitos e ano inteiro, só MG e só a janela do estudo.
def _chave(df, rotulo):
    cod = (df["CODMUNRES"].astype("string").str.strip()
           .str.replace(r"\.0+$", "", regex=True).str.replace(r"\D", "", regex=True))
    # código de 7 dígitos (IBGE) vira 6 tirando o verificador — mesma ponte do merge_fontes
    cod = cod.where(cod.str.len() != 7, cod.str[:6]).str.zfill(6)
    ano = pd.to_numeric(df["ano"], errors="coerce")
    # "310000" é "município ignorado – MG" no DATASUS, não um município: sairia como o 854º
    ignorado = cod.eq("310000").fillna(False)
    ok = cod.str.startswith("31", na=False) & (cod.str.len() == 6) & ~ignorado & ano.isin(list(ANOS))
    print(f"{rotulo}: {len(df):,} registros; descartados {int((~ok).sum()):,} "
          f"(dos quais {int(ignorado.sum()):,} com município ignorado 310000; o resto com "
          f"código fora de MG/inválido ou ano fora de {ANOS.start}–{ANOS.stop - 1})")
    out = df[ok].copy()
    out["cod_municipio_6"] = cod[ok]
    out["ano"] = ano[ok].astype("int64")
    return out.drop(columns="CODMUNRES")


# Percentual de `marcador` entre os registros com informação válida (`valido`), por município-ano.
def _proporcao(df, marcador, valido):
    chave = [df["cod_municipio_6"], df["ano"]]
    num = (marcador & valido).groupby(chave).sum()
    den = valido.groupby(chave).sum()
    return (num / den.where(den > 0) * 100).astype("float64")


# Agrega SINASC e SIM no grão município-ano com os 8 indicadores de saúde.
def calcular_indicadores_saude():
    sinasc = _chave(_ler("sinasc_mg.parquet", COLS_SINASC_USADAS), "SINASC")
    sim = _chave(_ler("sim_mg.parquet", COLS_SIM_USADAS), "SIM")

    peso = pd.to_numeric(sinasc["PESO"], errors="coerce")
    idade = pd.to_numeric(sinasc["IDADEMAE"], errors="coerce")
    parto = sinasc["PARTO"].astype("string").str.strip()
    consultas = sinasc["CONSULTAS"].astype("string").str.strip()
    escolaridade = sinasc["ESCMAE"].astype("string").str.strip()

    chave = [sinasc["cod_municipio_6"], sinasc["ano"]]
    base = pd.DataFrame({
        "nascidos_vivos": sinasc.groupby(chave).size(),
        "prop_cesarea": _proporcao(sinasc, parto == "2", parto.isin(["1", "2"])),
        "prop_baixo_peso": _proporcao(sinasc, peso < 2500, peso.between(200, 7000)),
        "prop_mae_adolescente": _proporcao(sinasc, idade <= 19, idade.between(10, 60)),
        "prop_prenatal_adequado": _proporcao(sinasc, consultas == "4",
                                             consultas.isin(["1", "2", "3", "4"])),
        "prop_mae_baixa_escolaridade": _proporcao(sinasc, escolaridade.isin(ESCOLARIDADE_BAIXA),
                                                  escolaridade.isin(["1", "2", "3", "4", "5"])),
    })
    infantis = sim[sim["obito_infantil"].fillna(False).astype(bool)]
    obitos = infantis.groupby(["cod_municipio_6", "ano"]).size().rename("obitos_infantis")

    df = base.join(obitos, how="outer")
    df.index.names = ["cod_municipio_6", "ano"]
    df = df.reset_index()
    sem_nascidos = df["nascidos_vivos"].isna()
    if sem_nascidos.any():
        print(f"ATENÇÃO: {int(sem_nascidos.sum())} município-ano com óbito infantil e nenhum "
              "nascido no SINASC — TMI fica nula nessas linhas.")
    df["nascidos_vivos"] = df["nascidos_vivos"].fillna(0).astype("int64")
    df["obitos_infantis"] = df["obitos_infantis"].fillna(0).astype("int64")
    df["tmi"] = df["obitos_infantis"] / df["nascidos_vivos"].where(df["nascidos_vivos"] > 0) * 1000

    colunas = ["cod_municipio_6", "ano", "nascidos_vivos", "obitos_infantis", "tmi",
               "prop_cesarea", "prop_baixo_peso", "prop_mae_adolescente",
               "prop_prenatal_adequado", "prop_mae_baixa_escolaridade"]
    df = df[colunas].sort_values(["cod_municipio_6", "ano"]).reset_index(drop=True)
    df.to_parquet(PROCESSED / "indicadores_saude_mg.parquet", index=False)

    print(f"\nIndicadores de saúde (grão município-ano): {len(df):,} linhas, "
          f"{df['cod_municipio_6'].nunique()} municípios")
    print(df.groupby("ano").agg(municipios=("cod_municipio_6", "nunique"),
                                nascidos=("nascidos_vivos", "sum"),
                                obitos_infantis=("obitos_infantis", "sum")).to_string())
    print(f"-> {PROCESSED / 'indicadores_saude_mg.parquet'}")
    return df


if __name__ == "__main__":
    calcular_indicadores_saude()
