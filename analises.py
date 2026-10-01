import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from config import INTERIM, FIGURES

COR_ROXO = "#534AB7"
COR_VERDE = "#1D9E75"
COR_VERMELHO = "#D9534F"
COR_LARANJA = "#E8A33D"

CAPITULOS_CID10 = {
    "A": "Infecciosas e parasitárias", "B": "Infecciosas e parasitárias",
    "P": "Afecções do período perinatal",
    "Q": "Malformações congênitas",
    "J": "Doenças respiratórias",
    "R": "Sintomas/sinais mal definidos",
}


def _linha(titulo):
    print("\n" + "=" * 60 + f"\n{titulo}\n" + "=" * 60)


def _salvar(fig, nome):
    fig.tight_layout()
    fig.savefig(FIGURES / nome, dpi=120)
    plt.close(fig)
    print(f"  -> figuras/{nome}")


def carregar():
    sinasc = pd.read_parquet(INTERIM / "sinasc_mg.parquet")
    sim = pd.read_parquet(INTERIM / "sim_mg.parquet")
    sinasc["PESO"] = pd.to_numeric(sinasc["PESO"], errors="coerce")
    sinasc["IDADEMAE"] = pd.to_numeric(sinasc["IDADEMAE"], errors="coerce")
    return sinasc, sim


def peso_ao_nascer(sinasc):
    _linha("Peso ao nascer")
    peso = sinasc["PESO"].dropna()
    peso_plausivel = peso[(peso >= 200) & (peso <= 7000)]
    baixo = (peso_plausivel < 2500).mean() * 100
    print(f"Baixo peso (<2500g): {baixo:.1f}% dos nascimentos com peso plausível")
    print(f"Mediana: {peso_plausivel.median():.0f} g")

    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(peso_plausivel, bins=60, color=COR_ROXO, edgecolor="white")
    ax.axvline(2500, color=COR_VERMELHO, linestyle="--", label="2.500 g (baixo peso)")
    ax.set_title("Distribuição do peso ao nascer (MG, 2010–2019)")
    ax.set_xlabel("peso (g)"); ax.set_ylabel("nascimentos")
    ax.legend()
    _salvar(fig, "peso_ao_nascer_hist.png")

    baixo_peso = sinasc["PESO"].between(200, 2499)
    por_ano = baixo_peso.groupby(sinasc["ano"]).mean() * 100
    fig, ax = plt.subplots(figsize=(8, 4))
    por_ano.plot(marker="o", ax=ax, color=COR_VERMELHO)
    ax.set_title("Baixo peso ao nascer por ano (%, MG)")
    ax.set_xlabel("ano"); ax.set_ylabel("% dos nascimentos (<2.500 g)")
    _salvar(fig, "baixo_peso_por_ano.png")


def tipo_parto(sinasc):
    _linha("Tipo de parto")
    mapa = {"1": "Vaginal", "2": "Cesáreo"}
    parto = sinasc["PARTO"].astype(str).map(mapa)
    print((parto.value_counts(normalize=True) * 100).round(1).to_string())

    por_ano = (parto.groupby(sinasc["ano"]).value_counts(normalize=True).unstack() * 100)
    fig, ax = plt.subplots(figsize=(8, 4))
    por_ano.plot(ax=ax, marker="o", color=[COR_VERMELHO, COR_ROXO])
    ax.set_title("Tipo de parto por ano (%, MG)")
    ax.set_xlabel("ano"); ax.set_ylabel("% dos nascimentos")
    ax.legend(title=None)
    _salvar(fig, "tipo_parto_por_ano.png")


def pre_natal(sinasc):
    _linha("Consultas de pré-natal")
    mapa = {"1": "Nenhuma", "2": "1 a 3", "3": "4 a 6", "4": "7 e mais"}
    consultas = sinasc["CONSULTAS"].astype(str).map(mapa)
    print((consultas.value_counts(normalize=True) * 100).round(1).to_string())

    adequado = (sinasc["CONSULTAS"].astype(str) == "4").groupby(sinasc["ano"]).mean() * 100
    fig, ax = plt.subplots(figsize=(8, 4))
    adequado.plot(marker="o", ax=ax, color=COR_VERDE)
    ax.set_title("Pré-natal adequado (7+ consultas) por ano (%, MG)")
    ax.set_xlabel("ano"); ax.set_ylabel("% dos nascimentos")
    _salvar(fig, "prenatal_adequado_por_ano.png")


def escolaridade_mae(sinasc):
    _linha("Escolaridade da mãe")
    mapa = {"1": "Nenhuma", "2": "1 a 3 anos", "3": "4 a 7 anos","4": "8 a 11 anos", "5": "12 e mais"}
    ordem = ["Nenhuma", "1 a 3 anos", "4 a 7 anos", "8 a 11 anos", "12 e mais"]
    esc = sinasc["ESCMAE"].astype(str).map(mapa)
    contagem = (esc.value_counts(normalize=True) * 100).round(1).reindex(ordem)
    print(contagem.to_string())

    fig, ax = plt.subplots(figsize=(8, 4))
    contagem.plot(kind="bar", ax=ax, color=COR_ROXO)
    ax.set_title("Escolaridade da mãe (%, MG, 2010–2019)")
    ax.set_xlabel(""); ax.set_ylabel("% dos nascimentos")
    plt.setp(ax.get_xticklabels(), rotation=20, ha="right")
    _salvar(fig, "escolaridade_mae.png")


def idade_mae(sinasc):
    _linha("Idade da mãe")
    idade = sinasc["IDADEMAE"]
    idade_plausivel = idade[(idade >= 10) & (idade <= 60)]
    print(f"Mediana: {idade_plausivel.median():.0f} anos")

    adolescente = idade.between(10, 19).groupby(sinasc["ano"]).mean() * 100
    fig, ax = plt.subplots(figsize=(8, 4))
    adolescente.plot(marker="o", ax=ax, color=COR_LARANJA)
    ax.set_title("Mães adolescentes (10–19 anos) por ano (%, MG)")
    ax.set_xlabel("ano"); ax.set_ylabel("% dos nascimentos")
    _salvar(fig, "maes_adolescentes_por_ano.png")


def causas_obito_infantil(sim):
    _linha("Causas de óbito infantil por capítulo CID-10 (aproximado)")
    obitos = sim.loc[sim["obito_infantil"], "CAUSABAS"].dropna().astype(str)
    capitulo = obitos.str[0].map(CAPITULOS_CID10).fillna("Outras")
    contagem = (capitulo.value_counts(normalize=True) * 100).round(1)
    print(contagem.to_string())

    fig, ax = plt.subplots(figsize=(8, 4.5))
    contagem.sort_values().plot(kind="barh", ax=ax, color=COR_VERDE)
    ax.set_title("Causas de óbito infantil por capítulo CID-10 (%, MG)")
    ax.set_xlabel("% dos óbitos infantis"); ax.set_ylabel("")
    _salvar(fig, "causas_obito_infantil.png")


def top_municipios_tmi(sinasc, sim, minimo_nascidos=3000, top_n=10):
    _linha(f"Municípios com maior TMI (mín. {minimo_nascidos:,} nascimentos no período)")
    nasc = sinasc.groupby("CODMUNRES", observed=True).size().rename("nascidos")
    ob = (sim.loc[sim["obito_infantil"]].groupby("CODMUNRES", observed=True).size().rename("obitos"))
    tabela = pd.concat([nasc, ob], axis=1).fillna(0)
    tabela["taxa_por_mil"] = (tabela["obitos"] / tabela["nascidos"] * 1000).round(1)

    relevante = (tabela[tabela["nascidos"] >= minimo_nascidos].sort_values("taxa_por_mil", ascending=False).head(top_n))
    print(relevante.to_string())
    print("\n(CODMUNRES bruto — sem nome de município: a tabela do IBGE ainda "
          "não foi incorporada ao pipeline)")

    fig, ax = plt.subplots(figsize=(8, 5))
    relevante["taxa_por_mil"].sort_values().plot(kind="barh", ax=ax, color=COR_VERMELHO)
    ax.set_title(f"Top {top_n} municípios por TMI (mín. {minimo_nascidos:,} ""nascimentos, MG 2010–2019)")
    ax.set_xlabel("óbitos infantis por mil nascidos"); ax.set_ylabel("CODMUNRES")
    _salvar(fig, "top_municipios_tmi.png")


def main():
    sinasc, sim = carregar()
    peso_ao_nascer(sinasc)
    tipo_parto(sinasc)
    pre_natal(sinasc)
    escolaridade_mae(sinasc)
    idade_mae(sinasc)
    causas_obito_infantil(sim)
    top_municipios_tmi(sinasc, sim)
    print("\nFiguras salvas em:", FIGURES)


if __name__ == "__main__":
    main()
