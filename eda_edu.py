"""
Análise exploratória dos indicadores de EDUCAÇÃO -> reports/figures.

Checagens de sanidade específicas desta parte (além das genéricas de %
ausência e linhas por ano):
  - municípios distintos por ano deve ficar perto de 853 (total de MG) — se
    vier muito diferente, o filtro de UF (regra 1 do transform_edu.py)
    provavelmente falhou.
  - IDEB é uma nota de 0 a 10 — qualquer valor fora dessa faixa é erro de
    parsing (coluna errada, vírgula/ponto trocado etc.), avisamos
    explicitamente em vez de deixar passar batido num gráfico.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from config import PROCESSED, FIGURES

N_MUNICIPIOS_MG = 853  # total de municípios de MG — referência para validar o filtro de UF


def _linha(titulo):
    print("\n" + "=" * 60 + f"\n{titulo}\n" + "=" * 60)


def _ausencia(df):
    return (df.isna().mean() * 100).round(1).sort_values(ascending=False)


def _checar_municipios_por_ano(df, rotulo, col_municipio="COD_MUNICIPIO", col_ano="ano"):
    contagem = df.groupby(col_ano)[col_municipio].nunique()
    print(f"\n[{rotulo}] municípios distintos por ano (esperado ~{N_MUNICIPIOS_MG}):")
    print(contagem.to_string())

    suspeitos = contagem[(contagem < N_MUNICIPIOS_MG * 0.9) | (contagem > N_MUNICIPIOS_MG * 1.05)]
    if not suspeitos.empty:
        print(f"  ATENÇÃO: contagem de municípios muito diferente de {N_MUNICIPIOS_MG} em "
              f"{list(suspeitos.index)} — suspeita de falha no filtro de UF ou "
              "linhas duplicadas. Confira _filtrar_mg() em transform_edu.py.")
    return contagem


def _checar_faixa_ideb(df, col):
    """IDEB é sempre uma nota entre 0 e 10 — fora disso é erro de parsing."""
    if col not in df.columns:
        return
    serie = df[col].dropna()
    if serie.empty:
        return
    fora = serie[(serie < 0) | (serie > 10)]
    if not fora.empty:
        print(f"  ATENÇÃO: {len(fora)} valores de {col} fora da faixa 0–10 "
              f"(nota do IDEB) — provável erro de parsing da coluna de origem. "
              f"Exemplos: {sorted(fora.unique())[:5]}")
    else:
        print(f"  OK: todos os {len(serie):,} valores de {col} estão entre 0 e 10.")


def _plotar_series_temporais(df):
    indicadores = {
        "IDEB_ANOS_INICIAIS": ("IDEB — anos iniciais (média MG)", "nota IDEB", "mean"),
        "IDEB_ANOS_FINAIS": ("IDEB — anos finais (média MG)", "nota IDEB", "mean"),
        "TAXA_DISTORCAO": ("Distorção idade-série (média MG)", "%", "mean"),
        "TAXA_ABANDONO": ("Taxa de abandono (média MG)", "%", "mean"),
        "TAXA_REPROVACAO": ("Taxa de reprovação (média MG)", "%", "mean"),
        "MATRICULAS": ("Matrículas totais em MG (soma)", "matrículas", "sum"),
    }
    for col, (titulo, eixo_y, como) in indicadores.items():
        if col not in df.columns or df[col].dropna().empty:
            continue
        agregacao = df.groupby("ano")[col].sum() if como == "sum" else df.groupby("ano")[col].mean()

        fig, ax = plt.subplots(figsize=(8, 4))
        agregacao.plot(marker="o", ax=ax, color="#534AB7")
        ax.set_title(titulo)
        ax.set_xlabel("ano"); ax.set_ylabel(eixo_y)
        # o IDEB é bienal: marca visualmente os anos sem dado (par) para não
        # parecer que a linha "pula" por erro
        if col.startswith("IDEB"):
            todos_anos = range(int(df["ano"].min()), int(df["ano"].max()) + 1)
            faltando = [a for a in todos_anos if a not in agregacao.index]
            if faltando:
                for a in faltando:
                    ax.axvline(a, color="lightgray", linestyle=":", linewidth=1, zorder=0)
        fig.tight_layout()
        fig.savefig(FIGURES / f"edu_serie_{col.lower()}.png", dpi=120)
        plt.close(fig)


def _plotar_distribuicao_municipios(df, col="IDEB_ANOS_INICIAIS"):
    """Boxplot por ano: mostra o quanto os municípios de MG variam entre si."""
    if col not in df.columns or df[col].dropna().empty:
        return
    anos = sorted(df["ano"].dropna().unique())
    dados_validos = [(a, df.loc[df["ano"] == a, col].dropna()) for a in anos]
    dados_validos = [(a, d) for a, d in dados_validos if len(d) > 0]
    if not dados_validos:
        return

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.boxplot([d for _, d in dados_validos],
               tick_labels=[str(int(a)) for a, _ in dados_validos])
    ax.set_title(f"Distribuição de {col} entre municípios de MG")
    ax.set_xlabel("ano"); ax.set_ylabel("nota IDEB")
    fig.tight_layout()
    fig.savefig(FIGURES / f"edu_distribuicao_{col.lower()}.png", dpi=120)
    plt.close(fig)


def _top_bottom_ideb(df, dim_municipio, col="IDEB_ANOS_INICIAIS", n=10):
    if col not in df.columns:
        return
    ultimo_ano = df.loc[df[col].notna(), "ano"].max()
    if pd.isna(ultimo_ano):
        return

    recorte = df[df["ano"] == ultimo_ano][["COD_MUNICIPIO", col]].dropna()
    if recorte.empty:
        return
    if dim_municipio is not None:
        recorte = recorte.merge(dim_municipio, on="COD_MUNICIPIO", how="left")

    top = recorte.nlargest(n, col)
    bottom = recorte.nsmallest(n, col)
    print(f"\nTop {n} municípios por {col} em {int(ultimo_ano)}:")
    print(top.to_string(index=False))
    print(f"\nBottom {n} municípios por {col} em {int(ultimo_ano)}:")
    print(bottom.to_string(index=False))


def eda_indicadores():
    caminho = PROCESSED / "indicadores_educacao_mg.parquet"
    if not caminho.exists():
        print(f"{caminho} não encontrado — rode transform_edu.py primeiro.")
        return None

    df = pd.read_parquet(caminho)
    dim_municipio_path = PROCESSED / "dim_municipio_edu_mg.parquet"
    dim_municipio = pd.read_parquet(dim_municipio_path) if dim_municipio_path.exists() else None

    _linha("EDUCAÇÃO — indicadores no grão município-ano")
    print(f"Dimensões: {df.shape[0]:,} linhas x {df.shape[1]} colunas")

    _checar_municipios_por_ano(df, "indicadores_educacao")

    print("\nLinhas por ano (cobertura da série):")
    print(df.groupby("ano").size().to_string())

    print("\nValores ausentes por coluna (%):")
    print(_ausencia(df).to_string())

    _linha("Checagem de sanidade — IDEB (nota de 0 a 10)")
    _checar_faixa_ideb(df, "IDEB_ANOS_INICIAIS")
    _checar_faixa_ideb(df, "IDEB_ANOS_FINAIS")

    _linha("Séries temporais e distribuição entre municípios")
    _plotar_series_temporais(df)
    _plotar_distribuicao_municipios(df, "IDEB_ANOS_INICIAIS")
    _plotar_distribuicao_municipios(df, "IDEB_ANOS_FINAIS")

    _linha("Top / bottom municípios por IDEB")
    _top_bottom_ideb(df, dim_municipio, "IDEB_ANOS_INICIAIS")
    _top_bottom_ideb(df, dim_municipio, "IDEB_ANOS_FINAIS")

    return df


def main():
    eda_indicadores()
    print("\nFiguras salvas em:", FIGURES)


if __name__ == "__main__":
    main()
