import pandas as pd
import pyarrow.parquet as pq

from config import (RAW, INTERIM, COLS_SINASC, COLS_SIM, IGNORADO_SINASC)

CATEGORICAS = {"CODMUNRES", "ESCMAE", "CONSULTAS", "PARTO", "TIPOBITO", "CAUSABAS"}

BATCH_SIZE = 500_000


def _colunas_para_ler(schema_cols, desejadas):
    desejadas_upper = {c.upper() for c in desejadas}
    return [c for c in schema_cols if c.upper() in desejadas_upper]


def _normalizar_2016plus(df):
    df = df.copy()
    df.columns = df.columns.str.upper()

    resultado = {}
    for nome in pd.unique(df.columns):
        mesmas = df.loc[:, df.columns == nome]
        if mesmas.shape[1] == 1:
            resultado[nome] = mesmas.iloc[:, 0]
        else:
            col = mesmas.iloc[:, 0]
            for i in range(1, mesmas.shape[1]):
                col = col.combine_first(mesmas.iloc[:, i])
            resultado[nome] = col

    out = pd.DataFrame(resultado)
    out = out.replace(["None", "nan", ""], pd.NA)
    return out


def _para_data(serie):
    return pd.to_datetime(serie.astype(str).str.zfill(8),
                          format="%d%m%Y", errors="coerce")


def _compactar(df):
    for col in df.columns.intersection(CATEGORICAS):
        df[col] = df[col].astype("category")
    return df


def _ler_em_lotes(caminho, cols_desejadas):
    pf = pq.ParquetFile(caminho)
    colunas = _colunas_para_ler(pf.schema_arrow.names, cols_desejadas)
    for batch in pf.iter_batches(columns=colunas, batch_size=BATCH_SIZE):
        chunk = batch.to_pandas()
        chunk = _normalizar_2016plus(chunk)
        yield chunk[cols_desejadas].copy()


def tratar_sinasc():
    lotes = []
    for chunk in _ler_em_lotes(RAW / "sinasc_mg.parquet", COLS_SINASC):
        chunk["CODMUNRES"] = chunk["CODMUNRES"].astype(str).str.zfill(6)
        chunk = chunk[chunk["CODMUNRES"].str.startswith("31")].copy()
        chunk["DTNASC"] = _para_data(chunk["DTNASC"])
        for col, sentinelas in IGNORADO_SINASC.items():
            chunk[col] = chunk[col].astype("string").str.strip().replace(sentinelas, pd.NA)
        if not chunk.empty:
            lotes.append(chunk)

    df = pd.concat(lotes, ignore_index=True)
    del lotes
    df = df.drop_duplicates()
    df = _compactar(df)
    df["ano"] = df["DTNASC"].dt.year
    df.to_parquet(INTERIM / "sinasc_mg.parquet", index=False)
    print(f"SINASC tratado: {df.shape[0]:,} linhas, {df.shape[1]} colunas")
    return df


def tratar_sim():
    lotes = []
    for chunk in _ler_em_lotes(RAW / "sim_mg.parquet", COLS_SIM):
        chunk["CODMUNRES"] = chunk["CODMUNRES"].astype(str).str.zfill(6)
        chunk = chunk[chunk["CODMUNRES"].str.startswith("31")].copy()
        chunk = chunk[chunk["TIPOBITO"].astype(str).str.strip() == "2"].copy()
        chunk["DTOBITO"] = _para_data(chunk["DTOBITO"])
        chunk["DTNASC"] = _para_data(chunk["DTNASC"])
        if not chunk.empty:
            lotes.append(chunk)

    df = pd.concat(lotes, ignore_index=True)
    del lotes
    df = df.drop_duplicates()
    df = _compactar(df)
    df["ano"] = df["DTOBITO"].dt.year

    df["idade_dias"] = (df["DTOBITO"] - df["DTNASC"]).dt.days
    df["obito_infantil"] = df["idade_dias"].between(0, 364)

    df.to_parquet(INTERIM / "sim_mg.parquet", index=False)
    print(f"SIM tratado: {df.shape[0]:,} linhas | óbitos infantis: "
          f"{int(df['obito_infantil'].sum()):,}")
    return df


def main():
    tratar_sinasc()
    tratar_sim()
    print("\nTratamento concluído. Arquivos em:", INTERIM)


if __name__ == "__main__":
    main()
