import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

from config import PROCESSED, FIGURES, ANOS

PARES = [
    {"id": "adolescencia_abandono", "curto": "Adolescência × Abandono", "saude": "prop_mae_adolescente", "educacao": "TAXA_ABANDONO",
     "titulo": "Mãe adolescente × Abandono escolar", "sinal": +1,
     "hipotese": "Onde a gravidez na adolescência é mais frequente, mais alunos abandonam a escola: "
                 "a gravidez interrompe a trajetória escolar e a evasão expõe à gravidez precoce."},
    {"id": "escolaridade_distorcao", "curto": "Escolaridade materna × Distorção", "saude": "prop_mae_baixa_escolaridade", "educacao": "TAXA_DISTORCAO",
     "titulo": "Baixa escolaridade materna × Distorção idade-série", "sinal": +1,
     "hipotese": "Onde as mães têm menos anos de estudo, mais alunos estão atrasados na escola "
                 "(transmissão intergeracional). Também testa se SINASC e INEP contam a mesma história."},
    {"id": "prenatal_ideb", "curto": "Pré-natal × IDEB", "saude": "prop_prenatal_adequado", "educacao": "IDEB_ANOS_INICIAIS",
     "titulo": "Pré-natal adequado × IDEB anos iniciais", "sinal": +1,
     "hipotese": "Atenção básica e anos iniciais do fundamental são responsabilidade do município: "
                 "quem organiza bem um serviço tende a organizar bem o outro."},
    {"id": "tmi_ideb", "curto": "TMI × IDEB", "saude": "tmi", "educacao": "IDEB_ANOS_INICIAIS",
     "titulo": "Mortalidade infantil × IDEB anos iniciais", "sinal": -1,
     "hipotese": "Os dois indicadores-síntese de cada área andam em sentidos opostos: "
                 "menor mortalidade infantil, maior qualidade do ensino."},
    {"id": "baixopeso_reprovacao", "curto": "Baixo peso × Reprovação", "saude": "prop_baixo_peso", "educacao": "TAXA_REPROVACAO",
     "titulo": "Baixo peso ao nascer × Reprovação", "sinal": +1,
     "hipotese": "Condições ao nascer afetam o desenvolvimento e o desempenho escolar. Hipótese mais "
                 "fraca no nível municipal (as coortes não coincidem no tempo): serve de contraste."},
]

ROTULOS = {
    "tmi": "TMI (por mil nascidos)", "prop_cesarea": "Cesárea (%)", "prop_baixo_peso": "Baixo peso (%)",
    "prop_mae_adolescente": "Mãe adolescente (%)", "prop_prenatal_adequado": "Pré-natal 7+ consultas (%)",
    "prop_mae_baixa_escolaridade": "Mãe com < 8 anos de estudo (%)",
    "IDEB_ANOS_INICIAIS": "IDEB anos iniciais", "IDEB_ANOS_FINAIS": "IDEB anos finais",
    "TAXA_DISTORCAO": "Distorção idade-série (%)", "TAXA_ABANDONO": "Abandono (%)",
    "TAXA_REPROVACAO": "Reprovação (%)", "MATRICULAS": "Matrículas",
}
PROPORCOES_SAUDE = ["prop_cesarea", "prop_baixo_peso", "prop_mae_adolescente",
                    "prop_prenatal_adequado", "prop_mae_baixa_escolaridade"]
MEDIAS_EDUCACAO = ["IDEB_ANOS_INICIAIS", "IDEB_ANOS_FINAIS", "TAXA_DISTORCAO", "TAXA_ABANDONO",
                   "TAXA_REPROVACAO", "MATRICULAS"]
PORTE_SENSIBILIDADE = 100
N_MINIMO = 30
ALFA = 0.05

AZUL, LARANJA, CINZA = "#2a78d6", "#eb6834", "#a3a29d"
TEXTO, TEXTO_2, GRADE, SUPERFICIE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"


# Lê o fato e a tabela de nomes de município (se existir).
def carregar(caminho=PROCESSED / "fato_indicadores.parquet"):
    if not caminho.exists():
        raise FileNotFoundError(f"{caminho} não encontrado — rode `python merge_fontes.py` antes.")
    fato = pd.read_parquet(caminho)
    num = [c for c in fato.columns if c not in ("cod_municipio_6", "cod_municipio", "cobertura", "ano")]
    fato[num] = fato[num].astype("float64")
    nomes = PROCESSED / "dim_municipio_edu_mg.parquet"
    if nomes.exists():
        dim = pd.read_parquet(nomes)
        dim = dim.assign(cod_municipio=dim["COD_MUNICIPIO"].astype("string").str[:7])
        fato = fato.merge(dim[["cod_municipio", "NOME_MUNICIPIO"]].drop_duplicates("cod_municipio"),
                          on="cod_municipio", how="left", validate="m:1")
        fato = fato.rename(columns={"NOME_MUNICIPIO": "nome_municipio"})
    else:
        fato["nome_municipio"] = pd.NA
    fato["nome_municipio"] = fato["nome_municipio"].fillna(fato["cod_municipio_6"]).astype("string")
    return fato


# Um registro por município com o período 2010–2019 consolidado.
def base_periodo(fato):
    g = fato.groupby(["cod_municipio_6", "cod_municipio", "nome_municipio"], dropna=False)
    base = g.agg(nascidos_vivos=("nascidos_vivos", "sum"), obitos_infantis=("obitos_infantis", "sum"),
                 **{c: (c, "mean") for c in MEDIAS_EDUCACAO}).reset_index()
    # TMI do período = óbitos somados / nascidos somados; média de TMIs anuais daria peso igual a ano com 3 nascidos
    base["tmi"] = base["obitos_infantis"] / base["nascidos_vivos"].where(base["nascidos_vivos"] > 0) * 1000
    for c in PROPORCOES_SAUDE:
        peso = fato["nascidos_vivos"].where(fato[c].notna())
        ponderada = (fato[c] * peso).groupby(fato["cod_municipio_6"]).sum(min_count=1)
        base[c] = base["cod_municipio_6"].map(ponderada / peso.groupby(fato["cod_municipio_6"]).sum())
    base["nascidos_ano"] = base["nascidos_vivos"] / len(ANOS)
    return base


# Recorte de um único ano, com as mesmas colunas da base do período.
def base_ano(fato, ano):
    base = fato[fato["ano"] == ano].copy()
    base["nascidos_ano"] = base["nascidos_vivos"]
    return base


# Mantém só municípios com pelo menos `minimo` nascidos por ano em média.
def filtrar_porte(base, minimo):
    return base[base["nascidos_ano"] >= minimo] if minimo else base


# Spearman com IC 95% (Fisher z, erro-padrão de Fieller) — None se n insuficiente.
def spearman(x, y):
    ok = x.notna() & y.notna()
    n = int(ok.sum())
    if n < N_MINIMO or x[ok].nunique() < 3 or y[ok].nunique() < 3:
        return {"n": n, "rho": np.nan, "p": np.nan, "ic_inf": np.nan, "ic_sup": np.nan}
    rho, p = stats.spearmanr(x[ok], y[ok])
    ep = np.sqrt(1.06 / (n - 3))
    z = np.arctanh(np.clip(rho, -0.9999, 0.9999))
    return {"n": n, "rho": rho, "p": p, "ic_inf": np.tanh(z - 1.96 * ep), "ic_sup": np.tanh(z + 1.96 * ep)}


# Ajuste de Holm para comparações múltiplas (controla o erro familiar).
def holm(p):
    p = pd.Series(p, dtype="float64")
    validos = p.dropna().sort_values()
    m = len(validos)
    ajustado = (validos * (m - np.arange(m))).cummax().clip(upper=1)
    return ajustado.reindex(p.index)


# Classificação verbal da força da correlação (faixas de Cohen).
def forca(rho):
    if pd.isna(rho):
        return "—"
    r = abs(rho)
    return "desprezível" if r < 0.1 else "fraca" if r < 0.3 else "moderada" if r < 0.5 else "forte"


# Calcula as correlações das combinações sobre uma base (período ou ano).
def correlacionar(base, pares=PARES):
    linhas = [{"id": p["id"], "titulo": p["titulo"], "saude": p["saude"], "educacao": p["educacao"],
               "sinal_esperado": p["sinal"], **spearman(base[p["saude"]], base[p["educacao"]])}
              for p in pares]
    res = pd.DataFrame(linhas)
    res["p_holm"] = holm(res["p"])
    res["significativa"] = res["p_holm"] < ALFA
    res["sentido_confere"] = np.sign(res["rho"]) == res["sinal_esperado"]
    res["forca"] = res["rho"].map(forca)
    return res


# Correlação de cada combinação ano a ano, para ver se a relação é estável no tempo.
def correlacao_por_ano(fato, pares=PARES, minimo=0):
    linhas = []
    for ano in sorted(fato["ano"].unique()):
        base = filtrar_porte(base_ano(fato, ano), minimo)
        for p in pares:
            linhas.append({"id": p["id"], "ano": int(ano), **spearman(base[p["saude"]], base[p["educacao"]])})
    return pd.DataFrame(linhas)


# Medianas de y por faixa (quantis) de x: tendência robusta sem ajustar modelo.
def tendencia_por_faixa(base, x, y, faixas=10):
    d = base[[x, y]].dropna()
    if len(d) < faixas * 3:
        return pd.DataFrame(columns=[x, y])
    grupo = pd.qcut(d[x].rank(method="first"), faixas, labels=False)
    return d.groupby(grupo).median()


# Estilo comum das figuras estáticas.
def _estilo():
    plt.rcParams.update({
        "figure.facecolor": SUPERFICIE, "axes.facecolor": SUPERFICIE, "savefig.facecolor": SUPERFICIE,
        "text.color": TEXTO, "axes.labelcolor": TEXTO_2, "xtick.color": TEXTO_2, "ytick.color": TEXTO_2,
        "axes.edgecolor": GRADE, "axes.spines.top": False, "axes.spines.right": False, "font.size": 10,
        "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlelocation": "left",
    })


# Salva a figura em reports/figures e fecha.
def _salvar(fig, nome):
    fig.savefig(FIGURES / nome, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> figuras/{nome}")


# Forest plot: ρ e IC 95% de cada combinação, base completa e com filtro de porte.
def figura_forest(resultados):
    _estilo()
    fig, ax = plt.subplots(figsize=(10, 4.6))
    cenarios = [("todos", AZUL, -0.15, "todos os municípios"),
                (f"porte>={PORTE_SENSIBILIDADE}", LARANJA, 0.15, f"≥ {PORTE_SENSIBILIDADE} nascidos/ano")]
    titulos = [p["titulo"] for p in PARES]
    for cenario, cor, desloc, rotulo in cenarios:
        r = resultados[resultados["cenario"] == cenario].set_index("id").loc[[p["id"] for p in PARES]]
        y = np.arange(len(r)) + desloc
        ax.hlines(y, r["ic_inf"], r["ic_sup"], color=cor, lw=2)
        ax.scatter(r["rho"], y, color=cor, s=46, zorder=3, label=rotulo,
                   facecolors=np.where(r["significativa"], cor, SUPERFICIE), linewidths=2)
    ax.axvline(0, color=TEXTO_2, lw=1)
    ax.set_yticks(range(len(titulos)), titulos)
    ax.invert_yaxis()
    ax.set_xlim(-1, 1)
    ax.grid(axis="x", color=GRADE, lw=0.8); ax.set_axisbelow(True)
    ax.set_xlabel("ρ de Spearman (IC 95%)")
    ax.legend(loc="lower right", frameon=False, fontsize=9)
    ax.set_title("Correlação saúde × educação nos municípios de MG, 2010–2019", fontsize=13, pad=10)
    ax.text(0, -0.2, "Ponto cheio: significativa após correção de Holm (α = 0,05); vazio: não significativa. "
            "Sem controle socioeconômico — associação, não causalidade.",
            transform=ax.transAxes, fontsize=8.5, color=TEXTO_2, va="top")
    _salvar(fig, "correlacoes_forest.png")


# Painel de dispersão das 5 combinações (período consolidado, todos os municípios).
def figura_dispersao(base, resultados):
    _estilo()
    fig, eixos = plt.subplots(2, 3, figsize=(15, 9))
    r = resultados[resultados["cenario"] == "todos"].set_index("id")
    for ax, p in zip(eixos.flat, PARES):
        d = base[[p["saude"], p["educacao"]]].dropna()
        ax.scatter(d[p["saude"]], d[p["educacao"]], s=9, color=AZUL, alpha=0.35, lw=0)
        t = tendencia_por_faixa(base, p["saude"], p["educacao"])
        ax.plot(t[p["saude"]], t[p["educacao"]], color=LARANJA, lw=2, marker="o", ms=4)
        ax.set_xlabel(ROTULOS[p["saude"]]); ax.set_ylabel(ROTULOS[p["educacao"]])
        ax.grid(color=GRADE, lw=0.6); ax.set_axisbelow(True)
        ax.set_title(p["titulo"])
        ax.text(0.98, 0.97, f"ρ = {r.loc[p['id'], 'rho']:.2f}  (n = {r.loc[p['id'], 'n']})".replace(".", ","),
                transform=ax.transAxes, ha="right", va="top", fontsize=10, weight="bold")
    eixo_nota = eixos.flat[-1]
    eixo_nota.axis("off")
    eixo_nota.text(0, 0.9, "Como ler", fontsize=11, weight="bold", va="top")
    eixo_nota.text(0, 0.78, "• cada ponto é um município, com os\n  indicadores consolidados de 2010–2019\n"
                   "• a linha laranja liga as medianas de\n  cada décimo do eixo horizontal\n"
                   "• ρ de Spearman: associação monotônica,\n  robusta a extremos",
                   fontsize=9.5, color=TEXTO_2, va="top", linespacing=1.5)
    fig.suptitle("Saúde × educação: as 5 combinações analisadas", x=0.01, ha="left", fontsize=14,
                 weight="bold")
    fig.tight_layout()
    _salvar(fig, "correlacoes_dispersao.png")


# Pequenos múltiplos: ρ ano a ano de cada combinação.
def figura_por_ano(por_ano):
    _estilo()
    fig, eixos = plt.subplots(1, len(PARES), figsize=(16, 3.6), sharey=True)
    for ax, p in zip(eixos, PARES):
        d = por_ano[(por_ano["id"] == p["id"])].dropna(subset=["rho"])
        ax.errorbar(d["ano"], d["rho"], yerr=[d["rho"] - d["ic_inf"], d["ic_sup"] - d["rho"]],
                    fmt="o", color=AZUL, ms=5, lw=1.5, capsize=0)
        ax.axhline(0, color=TEXTO_2, lw=1)
        ax.set_ylim(-1, 1)
        ax.set_xticks([2010, 2013, 2016, 2019])
        ax.grid(axis="y", color=GRADE, lw=0.6); ax.set_axisbelow(True)
        ax.set_title(p["titulo"].replace(" × ", " ×\n"), fontsize=9.5)
    eixos[0].set_ylabel("ρ de Spearman (IC 95%)")
    fig.suptitle("Estabilidade no tempo: correlação calculada ano a ano (IDEB só em anos ímpares)",
                 x=0.01, ha="left", fontsize=13, weight="bold")
    fig.tight_layout()
    _salvar(fig, "correlacoes_por_ano.png")


# Roda a análise completa: base do período, correlações, sensibilidade, ano a ano e figuras.
def main():
    fato = carregar()
    base = base_periodo(fato)
    base.to_parquet(PROCESSED / "municipio_periodo.parquet", index=False)
    print(f"Base do período: {len(base)} municípios (2010–2019 consolidado) "
          f"-> {PROCESSED / 'municipio_periodo.parquet'}")

    resultados = pd.concat([
        correlacionar(base).assign(cenario="todos"),
        correlacionar(filtrar_porte(base, PORTE_SENSIBILIDADE))
        .assign(cenario=f"porte>={PORTE_SENSIBILIDADE}"),
    ], ignore_index=True)
    resultados.to_csv(PROCESSED / "correlacoes_periodo.csv", index=False)
    por_ano = correlacao_por_ano(fato)
    por_ano.to_csv(PROCESSED / "correlacoes_por_ano.csv", index=False)

    for cenario, r in resultados.groupby("cenario", sort=False):
        print(f"\nCenário: {cenario} — ρ de Spearman, p ajustado por Holm (5 testes)")
        tabela = r[["titulo", "n", "rho", "ic_inf", "ic_sup", "p_holm", "forca", "sentido_confere"]]
        print(tabela.to_string(index=False, float_format=lambda v: f"{v:.3f}"))
    print("\nAssociação municipal, sem controle socioeconômico: não indica causalidade.")

    print("\nFiguras:")
    figura_forest(resultados)
    figura_dispersao(base, resultados)
    figura_por_ano(por_ano)
    return base, resultados, por_ano


if __name__ == "__main__":
    main()
