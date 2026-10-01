import pandas as pd

from config import PROCESSED, QUALIDADE, ANOS, N_MUNICIPIOS_MG

FONTES = {
    "datasus": {"rotulo": "saúde (DATASUS)",
                "arquivo": PROCESSED / "indicadores_saude_mg.parquet",
                "col_cod": "cod_municipio_6", "digitos": 6,
                "colunas": ["nascidos_vivos", "obitos_infantis", "tmi", "prop_cesarea",
                            "prop_baixo_peso", "prop_mae_adolescente",
                            "prop_prenatal_adequado", "prop_mae_baixa_escolaridade"]},
    "inep": {"rotulo": "educação (INEP)",
             "arquivo": PROCESSED / "indicadores_educacao_mg.parquet",
             "col_cod": "COD_MUNICIPIO", "digitos": 7,
             "colunas": ["IDEB_ANOS_INICIAIS", "IDEB_ANOS_FINAIS", "TAXA_DISTORCAO",
                         "TAXA_ABANDONO", "TAXA_REPROVACAO", "MATRICULAS"]},
}

CHAVE = ["cod_municipio_6", "ano"]
SAIDA = PROCESSED / "fato_indicadores.parquet"

ORDEM_CONFIANCA = ["ibge", "inep", "datasus"]
ESTRATEGIA_PADRAO = "source_priority"
SURVIVORSHIP = {
    "cod_municipio": "source_priority",
    "nome_municipio": "source_priority",
    "populacao": "most_complete",
}

TOLERANCIA_MUNICIPIOS = 0.02
FATOR_MAX_LINHAS = 1.3
LIMITE_NASCIDOS_PEQUENO = 100
FAIXAS = {
    "IDEB_ANOS_INICIAIS": (0, 10), "IDEB_ANOS_FINAIS": (0, 10),
    "TAXA_DISTORCAO": (0, 100), "TAXA_ABANDONO": (0, 100), "TAXA_REPROVACAO": (0, 100),
    "prop_cesarea": (0, 100), "prop_baixo_peso": (0, 100), "prop_mae_adolescente": (0, 100),
    "prop_prenatal_adequado": (0, 100), "prop_mae_baixa_escolaridade": (0, 100),
    "tmi": (0, 1000),
    "nascidos_vivos": (0, None), "obitos_infantis": (0, None), "MATRICULAS": (0, None),
}


# Imprime um título de etapa.
def _linha(titulo):
    print("\n" + "=" * 70 + f"\n{titulo}\n" + "=" * 70)


# Lê uma fonte e falha se faltar alguma coluna esperada.
def carregar(fonte, caminho=None):
    cfg = FONTES[fonte]
    caminho = caminho or cfg["arquivo"]
    if not caminho.exists():
        raise FileNotFoundError(f"{cfg['rotulo']}: arquivo não encontrado: {caminho}")
    df = pd.read_parquet(caminho)
    esperadas = [cfg["col_cod"], "ano", *cfg["colunas"]]
    faltando = [c for c in esperadas if c not in df.columns]
    if faltando:
        raise KeyError(f"{cfg['rotulo']}: colunas esperadas ausentes {faltando}. "
                       f"Disponíveis: {list(df.columns)}")
    return df


# Perfil por coluna: tipo, completude, distintos, unicidade, estatísticas ou exemplos.
def perfilar(df, fonte):
    registros = []
    for col in df.columns:
        s = df[col]
        preenchidos = int(s.notna().sum())
        distintos = int(s.nunique(dropna=True))
        reg = {"fonte": fonte, "coluna": col, "tipo": str(s.dtype), "linhas": len(s),
               "completude_pct": round(100 * preenchidos / len(s), 2) if len(s) else 0.0,
               "distintos": distintos,
               "unicidade_pct": round(100 * distintos / preenchidos, 2) if preenchidos else 0.0,
               "min": None, "mediana": None, "max": None, "exemplos": None}
        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
            reg.update(min=s.min(), mediana=s.median(), max=s.max())
        else:
            reg["exemplos"] = " | ".join(map(str, s.dropna().unique()[:3]))
        registros.append(reg)
    return pd.DataFrame(registros)


# Etapa 1: perfila cada fonte crua e salva o perfil consolidado.
def etapa_profiling(fontes, dir_qualidade=QUALIDADE):
    _linha("ETAPA 1 — PROFILING (fontes como chegaram, antes de qualquer tratamento)")
    perfis = []
    for fonte, df in fontes.items():
        cfg = FONTES[fonte]
        chave_bruta = [cfg["col_cod"], "ano"]
        perfil = perfilar(df, fonte)
        perfis.append(perfil)
        n_dup = int(df.duplicated(subset=chave_bruta).sum())
        print(f"\n{cfg['rotulo']}: {len(df):,} linhas x {df.shape[1]} colunas")
        print(perfil.drop(columns=["fonte", "linhas"]).to_string(index=False))
        print(f"  tipo da chave {cfg['col_cod']}: {df[cfg['col_cod']].dtype}"
              + ("  <- NUMÉRICO, será convertido para texto"
                 if pd.api.types.is_numeric_dtype(df[cfg["col_cod"]]) else ""))
        print(f"  chave {chave_bruta} duplicada (valores crus): "
              + (f"SIM — {n_dup} linha(s) repetida(s)" if n_dup else "não"))
    consolidado = pd.concat(perfis, ignore_index=True)
    dir_qualidade.mkdir(parents=True, exist_ok=True)
    destino = dir_qualidade / "perfil_fontes.csv"
    consolidado.to_csv(destino, index=False)
    print(f"\n  -> perfil consolidado salvo em {destino}")
    return consolidado


# Normaliza um código de município para texto só com dígitos, no tamanho dado.
def padronizar_codigo(serie, digitos):
    # chave é TEXTO: como número perde zero à esquerda e o join com a outra fonte falha em silêncio
    txt = (serie.astype("string").str.strip()
           .str.replace(r"\.0+$", "", regex=True)  # sufixo de leitura como float, antes de tirar não-dígitos
           .str.replace(r"\D", "", regex=True))
    return txt.where(txt.str.len() > 0).str.zfill(digitos)


# Etapa 2: chave canônica em texto, filtro de MG por prefixo e ano inteiro.
def padronizar(df, fonte):
    cfg = FONTES[fonte]
    out = df.copy()
    bruto = out[cfg["col_cod"]].astype("string")
    codigo = padronizar_codigo(out[cfg["col_cod"]], cfg["digitos"])
    alterados = int((bruto.fillna("") != codigo.fillna("")).sum())

    tamanho_ok = codigo.str.len() == cfg["digitos"]
    # filtro por prefixo "31", nunca pelo campo de UF: arquivos nacionais já vieram rotulados como MG
    eh_mg = codigo.str.startswith("31", na=False)
    ano = pd.to_numeric(out["ano"], errors="coerce")
    ano_ok = ano.notna() & (ano % 1 == 0) & ano.isin(list(ANOS))

    fora_uf = out.loc[tamanho_ok.fillna(False) & ~eh_mg, cfg["col_cod"]]
    manter = tamanho_ok.fillna(False) & eh_mg & ano_ok
    print(f"\n{cfg['rotulo']}:")
    print(f"  códigos reescritos pela padronização (tipo/'.0'/não-dígitos): {alterados:,}")
    print(f"  removidos por código vazio ou com tamanho != {cfg['digitos']}: "
          f"{int((~tamanho_ok.fillna(False)).sum()):,}")
    print(f"  removidos por não serem de MG (prefixo != 31): {len(fora_uf):,}"
          + (f"  ex.: {sorted(map(str, fora_uf.unique()))[:5]}" if len(fora_uf) else ""))
    print(f"  removidos por ano inválido ou fora de {ANOS.start}–{ANOS.stop - 1}: "
          f"{int((tamanho_ok.fillna(False) & eh_mg & ~ano_ok).sum()):,}")

    out[cfg["col_cod"]] = codigo
    out["ano"] = ano
    out = out[manter].copy()
    out["ano"] = out["ano"].astype("int64")
    out = out.rename(columns={cfg["col_cod"]: "cod_municipio" if cfg["digitos"] == 7 else CHAVE[0]})
    if out.empty:
        raise ValueError(f"{cfg['rotulo']}: nenhuma linha sobrou após a padronização.")
    print(f"  linhas mantidas: {len(out):,} | municípios: {out.iloc[:, 0].nunique():,}")
    return out


# Etapa 2 para todas as fontes.
def etapa_padronizacao(fontes):
    _linha("ETAPA 2 — PADRONIZAÇÃO (chave texto, MG pelo prefixo 31, ano inteiro)")
    return {f: padronizar(df, f) for f, df in fontes.items()}


# Uma linha por chave, ficando com o primeiro valor não-nulo de cada coluna.
def deduplicar(df, chave, rotulo):
    repetidas = df.duplicated(subset=chave, keep=False)
    n_chaves = int(df.loc[repetidas, chave].drop_duplicates().shape[0])
    print(f"\n{rotulo}: {n_chaves} chave(s) repetida(s) em {int(repetidas.sum())} linha(s)")
    if not n_chaves:
        return df.reset_index(drop=True)
    valores = [c for c in df.columns if c not in chave]
    divergencias = (df[repetidas].groupby(chave)[valores].nunique() > 1).sum()
    divergencias = divergencias[divergencias > 0]
    if len(divergencias):
        print("  ATENÇÃO: valores não-nulos divergentes entre as repetições "
              "(fica o primeiro):")
        print("  " + divergencias.to_string().replace("\n", "\n  "))
    # groupby.first pega o 1º NÃO-NULO por coluna; nunca soma/média: repetição não é nova medição
    out = df.groupby(chave, as_index=False, sort=True).first()
    print(f"  {len(df):,} -> {len(out):,} linhas")
    return out


# Etapa 3 para todas as fontes.
def etapa_deduplicacao(fontes):
    _linha("ETAPA 3 — DEDUPLICAÇÃO (uma linha por chave antes do merge)")
    chaves = {"datasus": CHAVE, "inep": ["cod_municipio", "ano"]}
    return {f: deduplicar(df, chaves[f], FONTES[f]["rotulo"]) for f, df in fontes.items()}


# Etapa 4: append columns por matching exato na chave 6 dígitos + ano.
def etapa_merge(saude, educacao):
    _linha("ETAPA 4 — MERGE (append columns, matching determinístico exato)")
    educacao = educacao.copy()
    # ponte 6->7: o código DATASUS é o IBGE sem o último dígito; trunca o INEP, nada de dígito verificador
    educacao[CHAVE[0]] = educacao["cod_municipio"].str[:6]
    ponte = educacao[[CHAVE[0], "cod_municipio"]].drop_duplicates()
    ambiguos = ponte[ponte.duplicated(CHAVE[0], keep=False)]
    if len(ambiguos):
        raise ValueError(f"Ponte 6->7 ambígua (mesmo código de 6 para dois de 7):\n{ambiguos}")
    ponte = ponte.set_index(CHAVE[0])["cod_municipio"]

    fato = saude.merge(educacao, on=CHAVE, how="outer", indicator=True,
                       suffixes=("_datasus", "_inep"), validate="1:1")
    fato["cobertura"] = fato.pop("_merge").map(
        {"both": "ambas", "left_only": "so_saude", "right_only": "so_educacao"}).astype("string")
    for col in ("nascidos_vivos", "obitos_infantis", "MATRICULAS"):
        if (fato[col].dropna() % 1 == 0).all():
            fato[col] = fato[col].astype("Int64")

    print(f"saúde {len(saude):,} linhas + educação {len(educacao):,} linhas "
          f"-> {len(fato):,} linhas (how='outer')")
    print("cobertura por município-ano:")
    print("  " + fato["cobertura"].value_counts().rename_axis(None).reindex(
        ["ambas", "so_saude", "so_educacao"], fill_value=0).to_string().replace("\n", "\n  "))
    mun_s, mun_e = set(saude[CHAVE[0]]), set(educacao[CHAVE[0]])
    for rotulo, exclusivos in (("só na saúde", mun_s - mun_e), ("só na educação", mun_e - mun_s)):
        print(f"municípios {rotulo}: {len(exclusivos)}"
              + (f"  ex.: {sorted(exclusivos)[:10]}" if exclusivos else ""))
    return fato, ponte


# Resolve um campo fornecido por mais de uma fonte segundo a estratégia registrada.
def resolver_campo(df, campo, fontes):
    colunas = {f: f"{campo}_{f}" for f in fontes if f"{campo}_{f}" in df.columns}
    estrategia = SURVIVORSHIP.get(campo, ESTRATEGIA_PADRAO)
    confianca = sorted(colunas, key=ORDEM_CONFIANCA.index)
    if estrategia == "source_priority":
        ordem = confianca
    elif estrategia == "most_complete":
        ordem = sorted(confianca, key=lambda f: -df[colunas[f]].notna().mean())
    else:
        raise ValueError(f"Estratégia de survivorship desconhecida para {campo}: {estrategia}")

    valores = df[[colunas[f] for f in ordem]]
    preenchidos = valores.notna().sum(axis=1)
    distintos = valores.astype("string").nunique(axis=1, dropna=True)
    conflitos = int(((preenchidos >= 2) & (distintos > 1)).sum())

    resultado = valores.iloc[:, 0].copy()
    origem = pd.Series(pd.NA, index=df.index, dtype="string").mask(resultado.notna(), ordem[0])
    for f in ordem[1:]:
        pegar = origem.isna() & df[colunas[f]].notna()
        resultado = resultado.mask(pegar, df[colunas[f]])
        origem = origem.mask(pegar, f)
    print(f"\n  {campo}: estratégia={estrategia}, ordem={ordem}")
    print(f"    conflitos reais (ambas preenchidas e diferentes): {conflitos}")
    print("    origem do valor final: "
          + ", ".join(f"{f}={int((origem == f).sum())}" for f in ordem)
          + f", nulo={int(origem.isna().sum())}")
    # remove só os nomes EXATOS sufixados: por prefixo, "cod_municipio" levaria junto "cod_municipio_6"
    out = df.drop(columns=list(colunas.values()))
    out[campo] = resultado
    return out


# Etapa 5: aplica survivorship aos campos repetidos e completa o código de 7 dígitos pela ponte.
def etapa_survivorship(fato, ponte, fontes=("datasus", "inep")):
    _linha("ETAPA 5 — SURVIVORSHIP (regra por campo quando >1 fonte fornece o mesmo campo)")
    print(f"ordem de confiança: {' > '.join(ORDEM_CONFIANCA)} | "
          f"padrão: {ESTRATEGIA_PADRAO} | registro: {SURVIVORSHIP}")
    sufixados = {c[:-len(f) - 1] for c in fato.columns for f in fontes if c.endswith(f"_{f}")}
    campos = sorted(c for c in sufixados
                    if sum(f"{c}_{f}" in fato.columns for f in fontes) >= 2)
    if not campos:
        print("\nNenhum campo é fornecido por mais de uma fonte: saúde e educação são "
              "complementares,\nentão não há conflito a resolver. As regras acima passam a "
              "valer quando o IBGE\nentrar como terceira fonte (nome, código de 7 dígitos, população).")
    for campo in campos:
        fato = resolver_campo(fato, campo, fontes)

    faltando = fato["cod_municipio"].isna()
    fato.loc[faltando, "cod_municipio"] = fato.loc[faltando, CHAVE[0]].map(ponte)
    print(f"\ncod_municipio (7 díg.) completado pela ponte do INEP em "
          f"{int((faltando & fato['cod_municipio'].notna()).sum())} linha(s) só-saúde; "
          f"sem código de 7 (município ausente do INEP): {int(fato['cod_municipio'].isna().sum())}")
    return fato


# Etapa 6: invariantes que, se quebrarem, apontam erro de merge.
def etapa_validacao(fato, tamanhos_fontes, dir_qualidade=QUALIDADE, n_esperado=N_MUNICIPIOS_MG):
    _linha("ETAPA 6 — VALIDAÇÃO (invariantes do merge)")
    falhas, violacoes = [], []

    n_mun = fato[CHAVE[0]].nunique()
    minimo = int(n_esperado * (1 - TOLERANCIA_MUNICIPIOS))
    ok = minimo <= n_mun <= n_esperado
    print(f"[{'OK' if ok else 'FALHA'}] (a) municípios distintos: {n_mun} "
          f"(esperado {minimo}–{n_esperado})")
    if not ok:
        falhas.append(f"(a) {n_mun} municípios distintos")

    n_dup = int(fato.duplicated(subset=CHAVE).sum())
    print(f"[{'OK' if not n_dup else 'FALHA'}] (b) chaves {CHAVE} duplicadas: {n_dup}")
    if n_dup:
        falhas.append(f"(b) {n_dup} chaves duplicadas")

    teto = int(max(tamanhos_fontes.values()) * FATOR_MAX_LINHAS)
    ok = len(fato) <= teto
    print(f"[{'OK' if ok else 'FALHA'}] (c) linhas: {len(fato):,} (teto {teto:,} = "
          f"{FATOR_MAX_LINHAS} x maior fonte, {tamanhos_fontes})")
    if not ok:
        falhas.append(f"(c) {len(fato):,} linhas > {teto:,}")

    print("(d) faixas plausíveis:")
    for col, (lo, hi) in FAIXAS.items():
        if col not in fato.columns:
            continue
        v = fato[col]
        fora = v.notna() & ((v < lo) | ((v > hi) if hi is not None else False))
        n_fora = int(fora.sum())
        print(f"  [{'OK' if not n_fora else 'FALHA'}] {col} em [{lo}, {hi if hi is not None else '∞'}]"
              + (f": {n_fora} fora — ex. {v[fora].head(3).tolist()}" if n_fora else ""))
        if n_fora:
            falhas.append(f"(d) {col}: {n_fora} fora da faixa")
            violacoes.append(fato.loc[fora, CHAVE + [col]].rename(columns={col: "valor"})
                             .assign(coluna=col, faixa=f"[{lo}, {hi}]"))

    if "nascidos_vivos" in fato.columns:
        pequenos = fato["nascidos_vivos"] < LIMITE_NASCIDOS_PEQUENO
        tmi_alta = pequenos & (fato["tmi"] > 100)
        print(f"\nNOTA INFORMATIVA (não é falha): {int(pequenos.sum()):,} município-ano têm menos de "
              f"{LIMITE_NASCIDOS_PEQUENO} nascidos vivos ({int(tmi_alta.sum())} deles com TMI > 100).\n"
              "  É instabilidade de número pequeno (1 óbito em 5 nascidos = 200 por mil), aritmética "
              "correta;\n  trate com filtro de porte na análise, não aqui.")

    if violacoes:
        destino = dir_qualidade / "violacoes_validacao.csv"
        pd.concat(violacoes, ignore_index=True).to_csv(destino, index=False)
        print(f"  -> violações salvas em {destino}")
    if falhas:
        raise ValueError("Validação falhou — fato_indicadores NÃO foi salvo:\n  "
                         + "\n  ".join(falhas))
    print("\nTodas as invariantes passaram.")


# Roda as 6 etapas e salva o fato município-ano.
def main(caminho_saude=None, caminho_edu=None, saida=SAIDA, dir_qualidade=QUALIDADE):
    brutas = {"datasus": carregar("datasus", caminho_saude),
              "inep": carregar("inep", caminho_edu)}
    etapa_profiling(brutas, dir_qualidade)
    padronizadas = etapa_padronizacao(brutas)
    unicas = etapa_deduplicacao(padronizadas)
    fato, ponte = etapa_merge(unicas["datasus"], unicas["inep"])
    fato = etapa_survivorship(fato, ponte)
    etapa_validacao(fato, {f: len(df) for f, df in unicas.items()}, dir_qualidade)

    primeiras = [*CHAVE, "cod_municipio", "cobertura"]
    fato = fato[primeiras + [c for c in fato.columns if c not in primeiras]]
    fato = fato.sort_values(CHAVE).reset_index(drop=True)
    fato.to_parquet(saida, index=False)
    print(f"\n{saida.name}: {fato.shape[0]:,} linhas x {fato.shape[1]} colunas -> {saida}")
    return fato


if __name__ == "__main__":
    main()
