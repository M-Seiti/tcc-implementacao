import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from config import PROCESSED, FIGURES

SUPERFICIE = "#fcfcfb"
TEXTO = "#0b0b0b"
TEXTO_2 = "#52514e"
GRADE = "#e4e3df"
AZUL = "#2a78d6"
LARANJA = "#eb6834"
AZUL_CLARO = "#cde2fb"
RAMPA_AZUL = LinearSegmentedColormap.from_list(
    "azul", ["#f0efec", "#9ec5f4", "#3987e5", "#1c5cab", "#0d366b"])

ORDEM_INDICADORES = [
    "nascidos_vivos", "obitos_infantis", "tmi", "prop_cesarea", "prop_baixo_peso",
    "prop_mae_adolescente", "prop_prenatal_adequado", "prop_mae_baixa_escolaridade",
    "IDEB_ANOS_INICIAIS", "IDEB_ANOS_FINAIS", "TAXA_DISTORCAO", "TAXA_ABANDONO",
    "TAXA_REPROVACAO", "MATRICULAS",
]
LIMITE_NASCIDOS_PEQUENO = 100

plt.rcParams.update({
    "figure.facecolor": SUPERFICIE, "axes.facecolor": SUPERFICIE, "savefig.facecolor": SUPERFICIE,
    "text.color": TEXTO, "axes.labelcolor": TEXTO_2, "xtick.color": TEXTO_2, "ytick.color": TEXTO_2,
    "axes.edgecolor": GRADE, "axes.spines.top": False, "axes.spines.right": False,
    "font.size": 11, "axes.titlesize": 14, "axes.titleweight": "bold", "axes.titlelocation": "left",
})


# Salva a figura em reports/figures e fecha.
def _salvar(fig, nome):
    fig.savefig(FIGURES / nome, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  -> figuras/{nome}")


# Desenha uma caixa com título e subtítulo centrados.
def _caixa(ax, x, y, w, h, titulo, sub="", cor=AZUL, fundo=SUPERFICIE, cor_titulo=TEXTO, tam=11.5):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0,rounding_size=0.08",
                                fc=fundo, ec=cor, lw=2))
    ax.text(x + w / 2, y + h * (0.64 if sub else 0.5), titulo, ha="center", va="center",
            fontsize=tam, weight="bold", color=cor_titulo)
    if sub:
        ax.text(x + w / 2, y + h * 0.3, sub, ha="center", va="center", fontsize=9, color=TEXTO_2,
                linespacing=1.3)


# Seta reta entre dois pontos.
def _seta(ax, xy0, xy1):
    ax.add_patch(FancyArrowPatch(xy0, xy1, arrowstyle="-|>", mutation_scale=14, color=TEXTO_2, lw=1.5))


# Fluxo das 6 etapas, das duas fontes até o fato, com o que cada etapa evita.
def pipeline(fato):
    fig, ax = plt.subplots(figsize=(16, 4.6))
    ax.set_xlim(0, 16); ax.set_ylim(0.6, 5.0); ax.axis("off")
    ax.text(0, 4.8, "Integração saúde + educação: 6 etapas de qualidade de dados",
            fontsize=15, weight="bold", va="top")

    _caixa(ax, 0.0, 3.0, 1.8, 1.1, "DATASUS", "saúde\nchave de 6 dígitos")
    _caixa(ax, 0.0, 1.3, 1.8, 1.1, "INEP", "educação\nchave de 7 dígitos")

    etapas = [("1. Profiling", "conhece o dado\nantes de tratar"),
              ("2. Padronização", "chave texto, MG\npelo prefixo 31"),
              ("3. Deduplicação", "1 linha por chave\nevita explosão"),
              ("4. Merge", "append columns\nmatching exato"),
              ("5. Survivorship", "regra por campo\nse fontes divergem"),
              ("6. Validação", "invariantes:\nerro de merge?")]
    x0, w, passo, y, h = 2.3, 1.78, 1.92, 2.05, 1.4
    _seta(ax, (1.8, 3.55), (x0, y + h * 0.7))
    _seta(ax, (1.8, 1.85), (x0, y + h * 0.3))
    for i, (titulo, sub) in enumerate(etapas):
        x = x0 + i * passo
        destaque = titulo.startswith("4.")
        _caixa(ax, x, y, w, h, titulo, sub, fundo=AZUL_CLARO if destaque else SUPERFICIE, tam=10)
        if i:
            _seta(ax, (x - passo + w, y + h / 2), (x, y + h / 2))

    xf = x0 + 6 * passo
    n_mun, n_lin = fato["cod_municipio_6"].nunique(), len(fato)
    _seta(ax, (xf - passo + w, y + h / 2), (xf, y + h / 2))
    _caixa(ax, xf, y - 0.1, 2.15, h + 0.2, "fato_indicadores",
           f"{n_mun} municípios\n× {fato['ano'].nunique()} anos = {n_lin:,} linhas".replace(",", "."),
           cor=LARANJA, tam=11)

    ax.text(x0, 0.95, "Etapas 2 e 3 acontecem ANTES do merge, em cada fonte separadamente; "
            "a 6 barra o resultado se alguma invariante quebrar (o fato não é salvo).",
            fontsize=9.5, color=TEXTO_2)
    _salvar(fig, "integracao_pipeline.png")


# Ponte 6→7 dígitos: trunca o código do INEP em vez de calcular o dígito verificador.
def ponte_codigo():
    fig, ax = plt.subplots(figsize=(13, 3.8))
    ax.set_xlim(0, 13); ax.set_ylim(0.4, 4.2); ax.axis("off")
    ax.text(0, 4.05, "Ponte entre as chaves: trunca o INEP, não calcula dígito verificador",
            fontsize=14, weight="bold", va="top")

    ax.text(0.2, 3.0, "INEP (código IBGE)", fontsize=10, color=TEXTO_2)
    for i, d in enumerate("3106200"):
        verificador = i == 6
        ax.add_patch(FancyBboxPatch((0.2 + i * 0.5, 2.0), 0.42, 0.7,
                                    boxstyle="round,pad=0,rounding_size=0.05",
                                    fc=SUPERFICIE, ec=LARANJA if verificador else AZUL, lw=2,
                                    ls="--" if verificador else "-"))
        ax.text(0.41 + i * 0.5, 2.35, d, ha="center", va="center", fontsize=16, weight="bold",
                color=TEXTO_2 if verificador else TEXTO)
    ax.text(3.41, 1.7, "dígito\nverificador", ha="center", va="top", fontsize=9, color=TEXTO_2)

    _seta(ax, (3.9, 2.35), (5.4, 2.35))
    ax.text(4.65, 2.6, "remove o\núltimo dígito", ha="center", va="bottom", fontsize=9, color=TEXTO_2)

    ax.text(5.6, 3.0, "chave de junção (= DATASUS)", fontsize=10, color=TEXTO_2)
    for i, d in enumerate("310620"):
        ax.add_patch(FancyBboxPatch((5.6 + i * 0.5, 2.0), 0.42, 0.7,
                                    boxstyle="round,pad=0,rounding_size=0.05",
                                    fc=AZUL_CLARO, ec=AZUL, lw=2))
        ax.text(5.81 + i * 0.5, 2.35, d, ha="center", va="center", fontsize=16, weight="bold")
    ax.text(5.6, 1.7, "Belo Horizonte: casa por igualdade\nexata com o código de 6 dígitos\n"
            "do SINASC/SIM (texto, não número)", fontsize=9.5, color=TEXTO_2,
            va="top")

    ax.text(9.8, 2.75, "Por que assim", fontsize=11, weight="bold")
    ax.text(9.8, 2.5, "• truncar é trivial e não erra;\n  calcular o verificador seria\n"
            "  reimplementar um algoritmo\n• o código de 7 que fica no fato\n  é o autêntico, do INEP\n"
            "• a ponte é conferida 1-para-1", fontsize=9.5, color=TEXTO_2, va="top", linespacing=1.4)
    _salvar(fig, "integracao_ponte_codigo.png")


# Completude por indicador e ano no fato: lacunas por desenho (IDEB bienal) ficam visíveis.
def completude(fato):
    cols = [c for c in ORDEM_INDICADORES if c in fato.columns]
    # notna() antes de agregar: colunas Float64/Int64 do INEP deixariam a tabela como object
    tabela = (fato[cols].notna().groupby(fato["ano"]).mean() * 100).astype("float64").T
    fig, ax = plt.subplots(figsize=(11, 6.2))
    im = ax.imshow(tabela.values, cmap=RAMPA_AZUL, vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(range(tabela.shape[1]), tabela.columns)
    ax.set_yticks(range(tabela.shape[0]), tabela.index)
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_xticks(np.arange(-.5, tabela.shape[1]), minor=True)
    ax.set_yticks(np.arange(-.5, tabela.shape[0]), minor=True)
    ax.grid(which="minor", color=SUPERFICIE, lw=2)
    ax.tick_params(which="minor", length=0)
    for (i, j), v in np.ndenumerate(tabela.values):
        if v < 99.5:
            ax.text(j, i, f"{v:.0f}%", ha="center", va="center", fontsize=8.5,
                    color=TEXTO if v < 55 else SUPERFICIE)
    cb = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cb.set_label("% de municípios com valor"); cb.outline.set_visible(False)
    ax.set_title("Completude do fato por indicador e ano (células sem rótulo = 100%)", pad=12)
    ax.text(0, -0.09, "IDEB vazio nos anos pares é a periodicidade do indicador (bienal), "
            "não falha de junção.", transform=ax.transAxes, fontsize=9.5, color=TEXTO_2, va="top")
    _salvar(fig, "integracao_completude.png")


# Funnel plot da TMI: a dispersão cresce quando há poucos nascidos (instabilidade de número pequeno).
def funil_tmi(fato):
    df = (fato[["nascidos_vivos", "obitos_infantis", "tmi"]].astype("float64").dropna()
          .query("nascidos_vivos > 0"))
    p = df["obitos_infantis"].sum() / df["nascidos_vivos"].sum()
    n = np.logspace(np.log10(df["nascidos_vivos"].min()), np.log10(df["nascidos_vivos"].max()), 300)
    dp = np.sqrt(p * (1 - p) / n)
    pequenos = (df["nascidos_vivos"] < LIMITE_NASCIDOS_PEQUENO).mean() * 100

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.scatter(df["nascidos_vivos"], df["tmi"], s=10, color=AZUL, alpha=0.35, lw=0)
    ax.axhline(p * 1000, color=TEXTO, lw=2)
    for z, rotulo in ((1.96, "95%"), (3.09, "99,8%")):
        ax.plot(n, (p + z * dp) * 1000, color=TEXTO_2, lw=1.5, ls="--")
        ax.plot(n, np.clip(p - z * dp, 0, None) * 1000, color=TEXTO_2, lw=1.5, ls="--")
        ax.text(n[0] * 1.12, (p + z * dp[0]) * 1000, f"limite {rotulo}", ha="left", va="bottom",
                fontsize=9, color=TEXTO_2)
    ax.text(n[0] * 1.12, p * 1000 + 4, f"MG: {p * 1000:.1f}‰".replace(".", ","), ha="left",
            va="bottom", fontsize=9.5, weight="bold")
    ax.axvline(LIMITE_NASCIDOS_PEQUENO, color=LARANJA, lw=2)
    ax.text(LIMITE_NASCIDOS_PEQUENO * 0.92, ax.get_ylim()[1] * 0.97,
            f"< {LIMITE_NASCIDOS_PEQUENO} nascidos:\n{pequenos:.0f}% dos município-ano",
            ha="right", va="top", fontsize=10, color=TEXTO)
    ax.set_xscale("log")
    ax.set_xlabel("nascidos vivos no município-ano (escala log)")
    ax.set_ylabel("TMI (óbitos infantis por mil nascidos)")
    ax.grid(axis="y", color=GRADE, lw=0.8); ax.set_axisbelow(True)
    ax.set_title("TMI × porte: abaixo de ~100 nascidos a taxa oscila por acaso, não por erro", pad=12)
    ax.text(0, -0.12, "Cada ponto é um município-ano. Linhas tracejadas: limites de controle "
            "binomiais em torno da taxa estadual.", transform=ax.transAxes, fontsize=9.5,
            color=TEXTO_2, va="top")
    _salvar(fig, "integracao_funil_tmi.png")


# Gera todas as figuras da integração a partir do fato salvo pelo merge_fontes.py.
def main(caminho=PROCESSED / "fato_indicadores.parquet"):
    if not caminho.exists():
        raise FileNotFoundError(f"{caminho} não encontrado — rode `python merge_fontes.py` antes.")
    fato = pd.read_parquet(caminho)
    print("Figuras da integração:")
    pipeline(fato)
    ponte_codigo()
    completude(fato)
    funil_tmi(fato)
    print("Figuras salvas em:", FIGURES)


if __name__ == "__main__":
    main()
