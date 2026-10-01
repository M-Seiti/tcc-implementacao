import pandas as pd

df = pd.read_parquet(
    "data/raw/sinasc_mg.parquet",
    columns=["CODMUNRES", "_ano_arquivo"]
)
print("Carregou:", df.shape)

df["CODMUNRES"] = df["CODMUNRES"].astype(str).str.zfill(6)
mg = df[df["CODMUNRES"].str.startswith("31")]

print("\nNascimentos MG por ano (contando linhas):")
print(mg.groupby("_ano_arquivo").size())
