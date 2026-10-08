import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import ANOS
from correlacoes import (PARES, ROTULOS, ALFA, AZUL, LARANJA, carregar, base_periodo, base_ano,
                         filtrar_porte, correlacionar, correlacao_por_ano, tendencia_por_faixa)

PERIODO = "2010–2019 consolidado"
OPCOES_PORTE = [0, 10, 25, 50, 100, 250, 500]

st.set_page_config(page_title="Saúde × Educação em MG", page_icon="📊", layout="wide")


# Carrega o fato e a base do período uma única vez por sessão do servidor.
@st.cache_data(show_spinner="Carregando o fato_indicadores…")
def dados():
    fato = carregar()
    return fato, base_periodo(fato)


# Correlação ano a ano para um porte mínimo (cacheada por porte).
@st.cache_data(show_spinner=False)
def por_ano(_fato, minimo):
    return correlacao_por_ano(_fato, minimo=minimo)


# Cor de destaque legível no tema claro e no escuro.
def cor_destaque():
    tema = getattr(getattr(st.context, "theme", None), "type", "light")
    return "#ffffff" if tema == "dark" else "#0b0b0b"


# Formata número no padrão brasileiro.
def br(valor, casas=2):
    if pd.isna(valor):
        return "—"
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


# Layout base dos gráficos plotly.
def _layout(fig, altura, titulo_x="", titulo_y=""):
    fig.update_layout(height=altura, margin=dict(l=10, r=10, t=40, b=10), hovermode="closest",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                      xaxis_title=titulo_x, yaxis_title=titulo_y)
    return fig


# Forest plot do recorte atual: ρ e IC 95%, ponto cheio quando significativa (Holm).
def grafico_forest(res):
    r = res.dropna(subset=["rho"]).iloc[::-1]
    fig = go.Figure(go.Scatter(
        x=r["rho"], y=r["titulo"], mode="markers",
        error_x=dict(type="data", symmetric=False, array=r["ic_sup"] - r["rho"],
                     arrayminus=r["rho"] - r["ic_inf"], thickness=2, width=0, color=AZUL),
        marker=dict(size=12, color=AZUL, line=dict(color=AZUL, width=2),
                    symbol=np.where(r["significativa"], "circle", "circle-open")),
        customdata=np.stack([r["ic_inf"], r["ic_sup"], r["p_holm"], r["n"]], axis=1),
        hovertemplate="<b>ρ = %{x:.2f}</b><br>IC 95%: %{customdata[0]:.2f} a %{customdata[1]:.2f}"
                      "<br>p (Holm) = %{customdata[2]:.3g}<br>n = %{customdata[3]}<extra>%{y}</extra>",
        showlegend=False))
    fig.add_vline(x=0, line_width=1, line_color="gray")
    fig.update_xaxes(range=[-1, 1], zeroline=False)
    return _layout(fig, 360, "ρ de Spearman (IC 95%)")


# Dispersão de uma combinação com a tendência por faixas e o município em destaque.
def grafico_dispersao(base, par, destaque):
    x, y = par["saude"], par["educacao"]
    d = base.dropna(subset=[x, y])
    fig = go.Figure(go.Scattergl(
        x=d[x], y=d[y], mode="markers", name="municípios",
        marker=dict(size=7, color=AZUL, opacity=0.5),
        customdata=np.stack([d["nome_municipio"], d["nascidos_ano"]], axis=1),
        hovertemplate=f"<b>%{{customdata[0]}}</b><br>{ROTULOS[x]}: %{{x:.2f}}<br>{ROTULOS[y]}: %{{y:.2f}}"
                      "<br>nascidos/ano: %{customdata[1]:.0f}<extra></extra>"))
    t = tendencia_por_faixa(d, x, y)
    if len(t):
        fig.add_trace(go.Scatter(x=t[x], y=t[y], mode="lines+markers", name="mediana por décimo",
                                 line=dict(color=LARANJA, width=3), marker=dict(size=7),
                                 hovertemplate="mediana: %{y:.2f}<extra></extra>"))
    sel = d[d["nome_municipio"] == destaque]
    if len(sel):
        cor = cor_destaque()
        fig.add_trace(go.Scatter(x=sel[x], y=sel[y], mode="markers+text", name=destaque,
                                 text=sel["nome_municipio"], textposition="top center",
                                 textfont=dict(color=cor, size=13),
                                 marker=dict(size=15, color=cor, line=dict(color=AZUL, width=3)),
                                 hovertemplate=f"<b>{destaque}</b><br>%{{x:.2f}} × %{{y:.2f}}<extra></extra>"))
    return _layout(fig, 470, ROTULOS[x], ROTULOS[y])


# ρ ano a ano de uma combinação, com o ano do recorte destacado.
def grafico_por_ano(pa, par, ano_sel):
    d = pa[pa["id"] == par["id"]].dropna(subset=["rho"])
    cores = [LARANJA if a == ano_sel else AZUL for a in d["ano"]]
    fig = go.Figure(go.Scatter(
        x=d["ano"], y=d["rho"], mode="markers", marker=dict(size=10, color=cores),
        error_y=dict(type="data", symmetric=False, array=d["ic_sup"] - d["rho"],
                     arrayminus=d["rho"] - d["ic_inf"], thickness=2, width=0, color=AZUL),
        customdata=d["n"], hovertemplate="<b>ρ = %{y:.2f}</b><br>%{x} · n = %{customdata}<extra></extra>",
        showlegend=False))
    fig.add_hline(y=0, line_width=1, line_color="gray")
    fig.update_yaxes(range=[-1, 1]); fig.update_xaxes(dtick=1)
    return _layout(fig, 470, "ano", "ρ de Spearman (IC 95%)")


# Conteúdo de uma aba de combinação.
def aba_combinacao(par, base, res, pa, destaque, ano_sel):
    r = res.set_index("id").loc[par["id"]]
    sentido = "positiva (os dois sobem juntos)" if par["sinal"] > 0 else "negativa (um sobe, o outro desce)"
    st.markdown(f"**Hipótese.** {par['hipotese']}  \n**Sentido esperado:** correlação {sentido}.")
    if pd.isna(r["rho"]):
        aviso = " O IDEB só existe em anos ímpares." if "IDEB" in par["educacao"] and ano_sel and ano_sel % 2 == 0 else ""
        st.info(f"Dados insuficientes neste recorte (n = {r['n']}).{aviso} Mude o ano ou reduza o porte mínimo.")
        return
    c = st.columns(4)
    c[0].metric("ρ de Spearman", br(r["rho"]))
    c[0].caption(f"correlação {r['forca']}")
    c[1].metric("IC 95%", f"{br(r['ic_inf'])} a {br(r['ic_sup'])}")
    c[2].metric("p ajustado (Holm)", "< 0,001" if r["p_holm"] < 0.001 else br(r["p_holm"], 3))
    c[2].caption("significativa" if r["significativa"] else "não significativa")
    c[3].metric("Municípios (n)", f"{int(r['n'])}")
    c[3].caption("sentido confere com a hipótese" if r["sentido_confere"] else "sentido contrário à hipótese")
    esq, dir_ = st.columns([3, 2])
    with esq:
        st.markdown("##### Cada ponto é um município")
        st.plotly_chart(grafico_dispersao(base, par, destaque), use_container_width=True,
                        theme="streamlit", key=f"disp_{par['id']}")
    with dir_:
        st.markdown("##### A relação se mantém ano a ano?")
        st.plotly_chart(grafico_por_ano(pa, par, ano_sel), use_container_width=True,
                        theme="streamlit", key=f"ano_{par['id']}")
    with st.expander("Ver os dados desta combinação"):
        cols = ["nome_municipio", "cod_municipio", "nascidos_ano", par["saude"], par["educacao"]]
        tabela = base[cols].dropna(subset=[par["saude"], par["educacao"]]).sort_values(par["saude"])
        tabela = tabela.rename(columns={"nome_municipio": "município", "cod_municipio": "código IBGE",
                                        "nascidos_ano": "nascidos/ano", **ROTULOS})
        st.dataframe(tabela, hide_index=True, use_container_width=True)
        st.download_button("Baixar CSV", tabela.to_csv(index=False).encode("utf-8"),
                           file_name=f"{par['id']}.csv", mime="text/csv", key=f"csv_{par['id']}")


# Aba de resumo: as 5 combinações lado a lado.
def aba_resumo(res):
    validas = res.dropna(subset=["rho"])
    n_sig = int(validas["significativa"].sum())
    n_sentido = int((validas["significativa"] & validas["sentido_confere"]).sum())
    st.markdown(f"**{n_sig} de {len(validas)}** combinações têm correlação significativa após a correção "
                f"de Holm (α = {br(ALFA)}); **{n_sentido}** delas no sentido da hipótese. "
                "Ponto cheio = significativa; vazio = não significativa.")
    st.plotly_chart(grafico_forest(res), use_container_width=True, theme="streamlit", key="forest")
    tabela = res[["titulo", "n", "rho", "ic_inf", "ic_sup", "p_holm", "forca", "sentido_confere"]].copy()
    tabela["p_holm"] = tabela["p_holm"].map(lambda p: "< 0,001" if p < 0.001 else br(p, 3))
    st.dataframe(tabela, hide_index=True, use_container_width=True, column_config={
        "titulo": "combinação", "rho": st.column_config.NumberColumn("ρ", format="%.2f"),
        "ic_inf": st.column_config.NumberColumn("IC inf.", format="%.2f"),
        "ic_sup": st.column_config.NumberColumn("IC sup.", format="%.2f"),
        "p_holm": "p (Holm)",
        "forca": "força", "sentido_confere": "sentido confere?"})


# Aba de metodologia e limitações.
def aba_metodologia():
    st.markdown("""
**Base.** `fato_indicadores.parquet` (853 municípios × 2010–2019), integrado pelo `merge_fontes.py`:
DATASUS (SINASC e SIM) + INEP, pareamento determinístico pelo código IBGE.

**Recorte consolidado (padrão).** Cada município vira um ponto com o período inteiro:
a TMI soma óbitos e nascidos de 2010–2019 antes de dividir; as proporções de saúde são médias
ponderadas pelos nascidos; IDEB e taxas do INEP são a média dos anos disponíveis. Isso evita contar
o mesmo município 10 vezes e reduz a instabilidade de município pequeno.

**Recorte por ano.** Mesma conta com um único ano — mais ruidoso, serve para ver se a relação
é estável no tempo. O IDEB só existe em anos ímpares.

**Correlação.** ρ de Spearman (relação monotônica, robusta a extremos e assimetria), IC 95% por
transformação de Fisher. As 5 combinações foram escolhidas **antes** de olhar os dados; o p-valor é
ajustado por **Holm** para os 5 testes.

**Porte mínimo.** Exclui municípios com poucos nascidos por ano, onde a taxa oscila por acaso.
Compare o resultado com e sem filtro: se o sinal se mantém, a conclusão é robusta.

**Limitações.**
- **Sem controle socioeconômico** (decisão de escopo): saúde e educação podem estar correlacionadas
  porque ambas acompanham a renda e o desenvolvimento do município. Os resultados são
  **associações**, não efeitos causais.
- **Falácia ecológica:** a unidade é o município; nada se conclui sobre indivíduos.
- **Autocorrelação espacial:** municípios vizinhos se parecem, o que torna os p-valores otimistas.
- **Coortes diferentes:** os nascidos de um ano não são os alunos avaliados no mesmo ano.
""")


# Monta a página: filtros, indicadores do recorte e abas.
def main():
    try:
        fato, periodo = dados()
    except FileNotFoundError as erro:
        st.error(f"{erro}")
        st.stop()

    st.title("Saúde × Educação nos municípios de Minas Gerais")
    st.caption("853 municípios · 2010–2019 · DATASUS (SINASC/SIM) + INEP · correlação de Spearman")

    f1, f2, f3 = st.columns([1.2, 1.4, 2])
    recorte = f1.selectbox("Recorte temporal", [PERIODO] + [str(a) for a in ANOS])
    porte = f2.select_slider("Porte mínimo (nascidos vivos por ano)", options=OPCOES_PORTE, value=0,
                             help="Abaixo de ~100 nascidos/ano a TMI oscila por acaso.")
    nomes = sorted(periodo["nome_municipio"].dropna().unique())
    destaque = f3.selectbox("Destacar município", ["(nenhum)"] + nomes)

    ano_sel = None if recorte == PERIODO else int(recorte)
    base = filtrar_porte(periodo if ano_sel is None else base_ano(fato, ano_sel), porte)
    res = correlacionar(base)
    pa = por_ano(fato, porte)

    k = st.columns(4)
    nascidos = base["nascidos_vivos"].sum()
    k[0].metric("Municípios no recorte", f"{len(base)}")
    k[1].metric("Nascidos vivos", br(nascidos, 0))
    k[2].metric("TMI do recorte (por mil)", br(base["obitos_infantis"].sum() / nascidos * 1000 if nascidos else np.nan, 1))
    k[3].metric("IDEB anos iniciais (mediana)", br(base["IDEB_ANOS_INICIAIS"].median(), 1))

    abas = st.tabs(["Resumo"] + [f"{i}. {p['curto']}" for i, p in enumerate(PARES, 1)] + ["Metodologia"])
    with abas[0]:
        aba_resumo(res)
    for aba, par in zip(abas[1:-1], PARES):
        with aba:
            aba_combinacao(par, base, res, pa, destaque, ano_sel)
    with abas[-1]:
        aba_metodologia()


main()
