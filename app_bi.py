import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import ANOS
from correlacoes import (PARES, ROTULOS, ALFA, DIRECAO, QUADRANTES, FAIXAS, CORES_QUADRANTE, carregar,
                         base_periodo, base_ano, filtrar_porte, correlacionar, correlacao_por_ano,
                         tendencia_por_faixa, classificar_quadrantes, classificar_faixas, limites_faixas,
                         tabela_classificacao)

PERIODO = "2010–2019 consolidado"
OPCOES_PORTE = [0, 10, 25, 50, 100, 250, 500]
SIMBOLOS = {"Crítico": "diamond", "Moderado – saúde": "triangle-up",
            "Moderado – educação": "square", "Não crítico": "circle"}
BADGE_QUADRANTE = {"Crítico": "red", "Moderado – saúde": "orange",
                   "Moderado – educação": "green", "Não crítico": "blue"}
BADGE_FAIXA = {"Adequada": "blue", "Atenção": "gray", "Alerta": "orange", "Grave": "red"}
PALETA = {
    "light": {"ink": "#0b0b0b", "quiet": "#3f4651", "accent": "#1d4ed8", "grid": "#d5dae2"},
    "dark": {"ink": "#f5f6f8", "quiet": "#c3c9d4", "accent": "#5b9cff", "grid": "#3a404c"},
}

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


# Tema ativo ("light" ou "dark"), para escolher cores com contraste em cada um.
def tema():
    t = getattr(getattr(st.context, "theme", None), "type", "light")
    return "dark" if t == "dark" else "light"


# Cores do tema ativo: texto, acento e quadrantes.
def cores():
    t = tema()
    return {**PALETA[t], "quadrante": CORES_QUADRANTE[t]}


# Formata número no padrão brasileiro.
def br(valor, casas=2):
    if pd.isna(valor):
        return "—"
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


# Rótulo colorido (badge) com a cor do tema para um quadrante ou faixa.
def badge(texto, cor):
    return f":{cor}-badge[{texto}]"


# Layout base dos gráficos plotly, com eixos e grade de alto contraste.
def _layout(fig, altura, titulo_x="", titulo_y=""):
    c = cores()
    fig.update_layout(height=altura, margin=dict(l=10, r=10, t=40, b=10), hovermode="closest",
                      font=dict(size=14, color=c["ink"]),
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(size=13)),
                      xaxis_title=titulo_x, yaxis_title=titulo_y)
    eixo = dict(gridcolor=c["grid"], linecolor=c["quiet"], tickfont=dict(color=c["ink"]),
                title_font=dict(color=c["ink"], size=14))
    fig.update_xaxes(**eixo)
    fig.update_yaxes(**eixo)
    return fig


# Forest plot do recorte atual: ρ e IC 95%, ponto cheio quando significativa (Holm).
def grafico_forest(res):
    acc = cores()["accent"]
    r = res.dropna(subset=["rho"]).iloc[::-1]
    fig = go.Figure(go.Scatter(
        x=r["rho"], y=r["titulo"], mode="markers",
        error_x=dict(type="data", symmetric=False, array=r["ic_sup"] - r["rho"],
                     arrayminus=r["rho"] - r["ic_inf"], thickness=2.5, width=0, color=acc),
        marker=dict(size=13, color=acc, line=dict(color=acc, width=2.5),
                    symbol=np.where(r["significativa"], "circle", "circle-open")),
        customdata=np.stack([r["ic_inf"], r["ic_sup"], r["p_holm"], r["n"]], axis=1),
        hovertemplate="<b>ρ = %{x:.2f}</b><br>IC 95%: %{customdata[0]:.2f} a %{customdata[1]:.2f}"
                      "<br>p (Holm) = %{customdata[2]:.3g}<br>n = %{customdata[3]}<extra>%{y}</extra>",
        showlegend=False))
    fig.add_vline(x=0, line_width=1.5, line_color=cores()["quiet"])
    fig.update_xaxes(range=[-1, 1], zeroline=False)
    return _layout(fig, 360, "ρ de Spearman (IC 95%)")


# Dispersão em quadrantes: cor e símbolo por quadrante, medianas tracejadas, tendência e destaque.
def grafico_dispersao(base, par, destaque):
    c = cores()
    x, y = par["saude"], par["educacao"]
    d = base.dropna(subset=[x, y]).assign(quadrante=classificar_quadrantes(base, par))
    fig = go.Figure()
    for q in QUADRANTES:
        dq = d[d["quadrante"] == q]
        fig.add_trace(go.Scatter(
            x=dq[x], y=dq[y], mode="markers", name=f"{q} ({len(dq)})",
            marker=dict(size=8, color=c["quadrante"][q], symbol=SIMBOLOS[q], opacity=0.85),
            customdata=np.stack([dq["nome_municipio"], dq["nascidos_ano"]], axis=1) if len(dq) else None,
            hovertemplate=f"<b>%{{customdata[0]}}</b> · {q}<br>{ROTULOS[x]}: %{{x:.2f}}"
                          f"<br>{ROTULOS[y]}: %{{y:.2f}}<br>nascidos/ano: %{{customdata[1]:.0f}}<extra></extra>"))
    fig.add_vline(x=d[x].median(), line_width=1.5, line_dash="dash", line_color=c["ink"])
    fig.add_hline(y=d[y].median(), line_width=1.5, line_dash="dash", line_color=c["ink"])
    t = tendencia_por_faixa(d, x, y)
    if len(t):
        fig.add_trace(go.Scatter(x=t[x], y=t[y], mode="lines", name="tendência (mediana por décimo)",
                                 line=dict(color=c["ink"], width=2.5),
                                 hovertemplate="mediana: %{y:.2f}<extra></extra>"))
    sel = d[d["nome_municipio"] == destaque]
    if len(sel):
        fig.add_trace(go.Scatter(x=sel[x], y=sel[y], mode="markers+text", name=destaque,
                                 text=sel["nome_municipio"], textposition="top center",
                                 textfont=dict(color=c["ink"], size=14),
                                 marker=dict(size=18, color="rgba(0,0,0,0)", line=dict(color=c["ink"], width=3)),
                                 hovertemplate=f"<b>{destaque}</b><br>%{{x:.2f}} × %{{y:.2f}}<extra></extra>"))
    return _layout(fig, 500, ROTULOS[x], ROTULOS[y])


# ρ ano a ano de uma combinação, com o ano do recorte destacado.
def grafico_por_ano(pa, par, ano_sel):
    c = cores()
    d = pa[pa["id"] == par["id"]].dropna(subset=["rho"])
    marcas = [c["quadrante"]["Crítico"] if a == ano_sel else c["accent"] for a in d["ano"]]
    fig = go.Figure(go.Scatter(
        x=d["ano"], y=d["rho"], mode="markers", marker=dict(size=11, color=marcas),
        error_y=dict(type="data", symmetric=False, array=d["ic_sup"] - d["rho"],
                     arrayminus=d["rho"] - d["ic_inf"], thickness=2.5, width=0, color=c["accent"]),
        customdata=d["n"], hovertemplate="<b>ρ = %{y:.2f}</b><br>%{x} · n = %{customdata}<extra></extra>",
        showlegend=False))
    fig.add_hline(y=0, line_width=1.5, line_color=c["quiet"])
    fig.update_yaxes(range=[-1, 1]); fig.update_xaxes(dtick=1)
    return _layout(fig, 500, "ano", "ρ de Spearman (IC 95%)")


# Contagem de municípios por quadrante, com o rótulo colorido de cada um.
def resumo_quadrantes(quad):
    total = int(quad.notna().sum())
    cols = st.columns(4)
    for col, q in zip(cols, QUADRANTES):
        n = int((quad == q).sum())
        col.markdown(badge(q, BADGE_QUADRANTE[q]))
        col.metric(q, f"{n}", label_visibility="collapsed")
        col.caption(f"{br(100 * n / total, 1) if total else '—'}% dos municípios")


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

    quad = classificar_quadrantes(base, par)
    st.markdown("##### Classificação em quadrantes")
    st.caption("Corte na mediana de cada indicador entre os municípios do recorte (linhas tracejadas). "
               "Crítico: pior que a mediana nos dois; Moderado: pior em só um; Não crítico: em nenhum.")
    resumo_quadrantes(quad)

    esq, dir_ = st.columns([3, 2])
    with esq:
        st.markdown("##### Cada ponto é um município")
        st.plotly_chart(grafico_dispersao(base, par, destaque), use_container_width=True,
                        theme="streamlit", key=f"disp_{par['id']}")
    with dir_:
        st.markdown("##### A relação se mantém ano a ano?")
        st.plotly_chart(grafico_por_ano(pa, par, ano_sel), use_container_width=True,
                        theme="streamlit", key=f"ano_{par['id']}")
    with st.expander("Ver os municípios desta combinação"):
        filtro = st.multiselect("Quadrantes", QUADRANTES, default=QUADRANTES, key=f"q_{par['id']}")
        cols = ["nome_municipio", "cod_municipio", "nascidos_ano", par["saude"], par["educacao"]]
        tabela = base[cols].assign(quadrante=quad).dropna(subset=["quadrante"])
        tabela = tabela[tabela["quadrante"].isin(filtro)].sort_values(["quadrante", par["saude"]])
        tabela = tabela.round({"nascidos_ano": 0, par["saude"]: 2, par["educacao"]: 2})
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


# Barras: quantos municípios são críticos em 0, 1, …, 5 combinações.
def grafico_criticos(classe):
    c = cores()
    cont = classe["n_combinacoes_criticas"].value_counts().reindex(range(len(PARES) + 1), fill_value=0)
    fig = go.Figure(go.Bar(
        x=cont.index, y=cont.values, marker=dict(color=c["quadrante"]["Crítico"]),
        text=cont.values, textposition="outside", textfont=dict(color=c["ink"], size=14),
        hovertemplate="críticos em %{x} combinações: %{y} municípios<extra></extra>"))
    fig.update_xaxes(dtick=1)
    fig.update_yaxes(range=[0, cont.max() * 1.15 if cont.max() else 1])
    return _layout(fig, 360, "nº de combinações em que o município é crítico", "municípios")


# Aba de classificação: municípios críticos em várias combinações e faixas por indicador.
def aba_classificacao(base):
    classe = tabela_classificacao(base)
    st.markdown("#### Municípios críticos em várias combinações")
    st.caption("Para cada município, conta-se em quantas das 5 combinações ele está no quadrante Crítico "
               "(pior que a mediana nos dois indicadores).")
    esq, dir_ = st.columns([2, 3])
    with esq:
        st.plotly_chart(grafico_criticos(classe), use_container_width=True, theme="streamlit", key="criticos")
    with dir_:
        minimo = st.slider("Mostrar municípios críticos em pelo menos", 1, len(PARES), 3,
                           format="%d combinações")
        cols_q = [f"quadrante_{p['id']}" for p in PARES]
        top = classe[classe["n_combinacoes_criticas"] >= minimo].sort_values(
            ["n_combinacoes_criticas", "nascidos_ano"], ascending=[False, False])
        top = top[["nome_municipio", "cod_municipio", "n_combinacoes_criticas", *cols_q]].rename(
            columns={"nome_municipio": "município", "cod_municipio": "código IBGE",
                     "n_combinacoes_criticas": "nº críticas", **{f"quadrante_{p['id']}": p["curto"] for p in PARES}})
        st.caption(f"{len(top)} municípios")
        st.dataframe(top, hide_index=True, use_container_width=True, height=300)

    st.divider()
    st.markdown("#### Faixas por indicador")
    st.caption("Cada indicador é dividido em quatro faixas de igual tamanho (quartis), da melhor para a pior "
               "situação. Em indicadores em que valor alto é bom (pré-natal, IDEB), a ordem se inverte.")
    opcoes = list(DIRECAO)
    col = st.selectbox("Indicador", opcoes, format_func=lambda k: ROTULOS[k], index=opcoes.index("tmi"))
    serie = base[col]
    faixa = classificar_faixas(serie, col)
    limites = limites_faixas(serie, col)
    cs = st.columns(4)
    for cx, f, lim in zip(cs, FAIXAS, limites):
        cx.markdown(badge(f, BADGE_FAIXA[f]))
        cx.metric(f, f"{int((faixa == f).sum())}", label_visibility="collapsed")
        cx.caption(f"{ROTULOS[col]}: {lim}")
    filtro = st.multiselect("Faixas", FAIXAS, default=FAIXAS[2:], key="faixas_sel")
    tabela = base[["nome_municipio", "cod_municipio", "nascidos_ano", col]].assign(faixa=faixa)
    tabela = tabela[tabela["faixa"].isin(filtro)].sort_values(col, ascending=DIRECAO[col] < 0)
    tabela = tabela.round({"nascidos_ano": 0, col: 2})
    tabela = tabela.rename(columns={"nome_municipio": "município", "cod_municipio": "código IBGE",
                                    "nascidos_ano": "nascidos/ano", col: ROTULOS[col]})
    st.dataframe(tabela, hide_index=True, use_container_width=True, height=320)
    st.download_button("Baixar classificação completa (CSV)",
                       classe.to_csv(index=False).encode("utf-8"),
                       file_name="classificacao_municipios.csv", mime="text/csv", key="csv_classe")


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

**Quadrantes.** Em cada combinação, o município é comparado com a mediana dos municípios do recorte
em cada indicador, considerando o sentido de cada um (TMI alta é ruim; IDEB alto é bom):
**Crítico** = pior que a mediana nos dois; **Moderado – saúde** ou **Moderado – educação** = pior
só naquele; **Não crítico** = em nenhum dos dois.

**Faixas.** Cada indicador é dividido em quartis: **Adequada** (melhor 25%), **Atenção**,
**Alerta** e **Grave** (pior 25%). É uma classificação **relativa**: indica a posição do
município entre os de MG, e não o cumprimento de uma meta absoluta.

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
    st.caption("853 municípios · 2010–2019 · DATASUS (SINASC/SIM) + INEP · correlação de Spearman · "
               "tema claro/escuro: menu ⋮ → Settings → Theme")

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

    abas = st.tabs(["Resumo"] + [f"{i}. {p['curto']}" for i, p in enumerate(PARES, 1)]
                   + ["Classificação", "Metodologia"])
    with abas[0]:
        aba_resumo(res)
    for aba, par in zip(abas[1:6], PARES):
        with aba:
            aba_combinacao(par, base, res, pa, destaque, ano_sel)
    with abas[6]:
        aba_classificacao(base)
    with abas[7]:
        aba_metodologia()


main()
