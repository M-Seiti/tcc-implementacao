import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from config import INTERIM, FIGURES


def _linha(titulo):
    print("\n" + "=" * 60 + f"\n{titulo}\n" + "=" * 60)


def _ausencia(df):
    return (df.isna().mean() * 100).round(1).sort_values(ascending=False)


def eda_sinasc():
    df = pd.read_parquet(INTERIM / "sinasc_mg.parquet")
    _linha("SINASC — nascidos vivos")
    print(f"Dimensões: {df.shape[0]:,} linhas x {df.shape[1]} colunas")
    print(f"Municípios distintos (CODMUNRES): {df['CODMUNRES'].nunique()}")

    print("\nNascimentos por ano:")
    por_ano = df.groupby("ano").size()
    print(por_ano.to_string())

    print("\nValores ausentes por coluna (%):")
    print(_ausencia(df).to_string())

    peso = pd.to_numeric(df["PESO"], errors="coerce")
    fora = ((peso < 200) | (peso > 7000)).mean() * 100
    print(f"\nPeso fora de 200–7000 g: {fora:.2f}% "
          f"(mediana {peso.median():.0f} g)")

    idade = pd.to_numeric(df["IDADEMAE"], errors="coerce")
    print(f"Idade da mãe: min {idade.min():.0f}, mediana "
          f"{idade.median():.0f}, max {idade.max():.0f}")
    print(f"Nascimentos de mães < 20 anos: "
          f"{(idade < 20).mean() * 100:.1f}%")

    fig, ax = plt.subplots(figsize=(8, 4))
    por_ano.plot(kind="bar", ax=ax, color="#534AB7")
    ax.set_title("SINASC — nascidos vivos por ano (MG)")
    ax.set_xlabel("ano"); ax.set_ylabel("nascimentos")
    fig.tight_layout(); fig.savefig(FIGURES / "sinasc_nascimentos_por_ano.png", dpi=120)
    plt.close(fig)
    return df


def eda_sim(df_sinasc):
    df = pd.read_parquet(INTERIM / "sim_mg.parquet")
    _linha("SIM — óbitos (não-fetais)")
    print(f"Dimensões: {df.shape[0]:,} linhas x {df.shape[1]} colunas")

    print("\nÓbitos infantis (< 1 ano) por ano:")
    inf_ano = df[df["obito_infantil"]].groupby("ano").size()
    print(inf_ano.to_string())

    print("\nValores ausentes por coluna (%):")
    print(_ausencia(df).to_string())

    print(f"\nDatas de óbito inválidas (NaT): "
          f"{df['DTOBITO'].isna().mean() * 100:.2f}%")
    print(f"Datas de nascimento inválidas (NaT): "
          f"{df['DTNASC'].isna().mean() * 100:.2f}%")

    _linha("Prévia — taxa de mortalidade infantil por mil (MG)")
    num = (df[df["obito_infantil"]].groupby("ano").size()
           .rename("obitos_inf"))
    den = df_sinasc.groupby("ano").size().rename("nascidos")
    taxa = (num / den * 1000).round(1).rename("por_mil")
    print(pd.concat([num, den, taxa], axis=1).to_string())

    fig, ax = plt.subplots(figsize=(8, 4))
    taxa.plot(marker="o", ax=ax, color="#1D9E75")
    ax.set_title("Prévia — mortalidade infantil por mil (MG)")
    ax.set_xlabel("ano"); ax.set_ylabel("óbitos < 1 ano / mil nascidos")
    fig.tight_layout(); fig.savefig(FIGURES / "previa_mortalidade_infantil.png", dpi=120)
    plt.close(fig)


def main():
    df_sinasc = eda_sinasc()
    eda_sim(df_sinasc)
    print("\nFiguras salvas em:", FIGURES)


if __name__ == "__main__":
    main()
