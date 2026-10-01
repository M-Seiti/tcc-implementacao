"""
Extração dos dados brutos de EDUCAÇÃO (INEP) -> data/raw/

Diferente da saúde (PySUS baixa direto do DATASUS), não existe biblioteca de
download para o INEP: os arquivos (xlsx/csv/zip) precisam ser baixados
manualmente do portal do INEP e colocados em data/raw/edu/ antes de rodar
este script.

Este módulo só LÊ e converte para parquet — nenhuma transformação de dados
(filtro de UF, tipos, limpeza, seleção de colunas) acontece aqui, isso é
trabalho do transform_edu.py. A única exceção inevitável é achar a linha de
cabeçalho real dentro do Excel: as planilhas do INEP têm linhas de
título/legenda antes do cabeçalho, e sem detectar isso não dá nem para montar
um DataFrame retangular.

Arquivos usados (download.inep.gov.br, renomeados para casar com FONTES_EDU):
  - rendimento_municipios_<ano>.zip  <- Taxas de Rendimento Escolar, municípios
  - distorcao_municipios_<ano>.zip   <- Taxas de Distorção Idade-Série, municípios
  - sinopse_<ano>.zip                <- Sinopse Estatística da Educação Básica
  - ideb_anos_{iniciais,finais}_municipios_2019.zip <- IDEB 2019, municípios
    (portal_ideb/planilhas_para_download/2019/divulgacao_anos_*_municipios_2019.zip)
Os links por ano estão nas páginas de "Dados abertos > Indicadores
educacionais" e "Sinopses estatísticas" do INEP (gov.br/inep).
"""
import re
import unicodedata
import zipfile
from pathlib import Path

import pandas as pd
from tqdm.auto import tqdm

from config import RAW, RAW_EDU, FONTES_EDU, MARCADORES_CABECALHO_EDU

ANO_REGEX = re.compile(r"(20\d{2})")
EXTENSOES_DADOS = (".xlsx", ".xls", ".csv")


def _chave(valor):
    """Normaliza o texto de uma célula para comparação: maiúsculo, sem acento/espaço/underscore."""
    txt = unicodedata.normalize("NFKD", str(valor))
    txt = "".join(c for c in txt if not unicodedata.combining(c))
    return re.sub(r"[\s_]+", "", txt).upper()


MARCADORES_CHAVE = {_chave(m) for m in MARCADORES_CABECALHO_EDU}
NUMERO_REGEX = re.compile(r"^-?\d+([.,]\d+)?$")
COD_MUNICIPIO_REGEX = re.compile(r"^\d{7}(\.0)?$")


def _limpar_celula(valor):
    """Célula vazia/só espaço -> None; o resto vira texto com espaços colapsados."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return None
    txt = re.sub(r"\s+", " ", str(valor)).strip()
    return txt if txt and txt.lower() != "nan" else None


def _localizar_blocos(bruto, max_linhas=40):
    """
    Localiza o bloco de cabeçalho de uma aba lida com header=None.

    - início do cabeçalho: primeira linha com uma célula IGUAL a um marcador
      (ex.: "Código do Município", "CO_MUNICIPIO"); sobe enquanto as linhas de
      cima tiverem 2+ células preenchidas (rótulos-pai mesclados, ex.: "Taxa
      de Aprovação - 2010"), parando no título, que ocupa uma célula só.
    - início dos dados: primeira linha com um código de município (7 dígitos)
      na coluna do marcador; recua sobre linhas logo acima que sejam
      majoritariamente numéricas (totais Brasil/região/UF da sinopse, que não
      têm código). Não basta "primeira linha com um número": o cabeçalho do
      IDEB tem anos soltos (2007, 2009...) como rótulo das projeções.

    Devolve (inicio_cabecalho, linha_marcador, inicio_dados), ou None.
    """
    n = min(max_linhas, len(bruto))
    linha_marcador = col_marcador = None
    for i in range(n):
        for k, v in enumerate(bruto.iloc[i]):
            if _limpar_celula(v) and _chave(v) in MARCADORES_CHAVE:
                linha_marcador, col_marcador = i, k
                break
        if linha_marcador is not None:
            break
    if linha_marcador is None:
        return None

    inicio = linha_marcador
    while inicio > 0 and sum(_limpar_celula(v) is not None for v in bruto.iloc[inicio - 1]) >= 2:
        inicio -= 1

    def _majoritariamente_numerica(j):
        celulas = [c for c in map(_limpar_celula, bruto.iloc[j]) if c]
        return bool(celulas) and sum(bool(NUMERO_REGEX.match(c)) for c in celulas) * 2 > len(celulas)

    for j in range(linha_marcador + 1, n):
        if COD_MUNICIPIO_REGEX.match(_limpar_celula(bruto.iat[j, col_marcador]) or ""):
            while j - 1 > linha_marcador and _majoritariamente_numerica(j - 1):
                j -= 1
            return inicio, linha_marcador, j
    return None


def _nomes_colunas(cabecalho, linha_marcador):
    """
    Monta um nome por coluna a partir do bloco de cabeçalho (várias linhas).

    Se o bloco tiver uma linha de nomes técnicos (ex.: SG_UF, CO_MUNICIPIO,
    VL_OBSERVADO_2019 — só algumas edições têm), usa só ela. Senão concatena
    os rótulos das linhas com " | ". Rótulo-pai de célula mesclada só aparece
    na 1ª coluna do intervalo; ele é propagado para a direita apenas quando
    há sub-rótulos embaixo (senão é um rótulo-folha mesclado na vertical, que
    não deve vazar para as colunas vizinhas). Colunas de identificação
    (Ano, UF, Código do Município...) — rótulo na linha do marcador e nada
    embaixo — ficam só com esse rótulo: em algumas edições um rótulo-pai como
    "Taxa de Aprovação - 2012" começa na coluna 0 e as cobriria também.
    """
    linhas = [[_limpar_celula(v) for v in cabecalho.iloc[i]] for i in range(len(cabecalho))]
    for linha in linhas:
        if any(c and "_" in c and _chave(c) in MARCADORES_CHAVE for c in linha):
            return [c or f"_COL{k}" for k, c in enumerate(linha)]

    ncol = cabecalho.shape[1]
    preenchidas = []
    for i, linha in enumerate(linhas):
        nova, atual = [], None
        for k, c in enumerate(linha):
            if c is not None:
                tem_filhos = any(linhas[r][k] is not None for r in range(i + 1, len(linhas)))
                atual = c if tem_filhos else None
                nova.append(c)
            else:
                nova.append(atual)
        preenchidas.append(nova)

    nomes = []
    for k in range(ncol):
        rotulo_id = linhas[linha_marcador][k]
        if rotulo_id and all(linhas[r][k] is None for r in range(linha_marcador + 1, len(linhas))):
            nomes.append(rotulo_id)
            continue
        partes = []
        for linha in preenchidas:
            if linha[k] and linha[k] not in partes:
                partes.append(linha[k])
        nomes.append(" | ".join(partes) if partes else f"_COL{k}")
    return nomes


def _ler_planilha(caminho, abas_regex=None):
    """
    Lê um .xlsx/.xls do INEP. Percorre as abas (todas, ou só as que casam com
    abas_regex), acha o bloco de cabeçalho real de cada uma e empilha as abas
    que têm linhas de município. Abas sem cabeçalho reconhecível (capa,
    sumário, notas) são ignoradas.
    """
    livro = pd.ExcelFile(caminho)
    abas = [a for a in livro.sheet_names if abas_regex is None or re.search(abas_regex, a.strip())]
    partes = []
    for aba in abas:
        bruto = pd.read_excel(livro, sheet_name=aba, header=None, dtype=str)
        blocos = _localizar_blocos(bruto)
        if blocos is None:
            continue
        inicio, marcador, dados = blocos
        df = bruto.iloc[dados:].copy()
        df.columns = _nomes_colunas(bruto.iloc[inicio:dados], marcador - inicio)
        df = df.dropna(axis=1, how="all").dropna(axis=0, how="all")
        df["_aba_origem"] = aba
        partes.append(df)

    if not partes:
        raise ValueError(
            f"Nenhuma aba de {caminho.name} tem cabeçalho reconhecível (procurei uma "
            f"célula igual a {MARCADORES_CABECALHO_EDU}). Ajuste MARCADORES_CABECALHO_EDU "
            "em config.py ou abra o arquivo manualmente."
        )
    return pd.concat(partes, ignore_index=True)


def _ler_csv(caminho):
    """
    CSVs do INEP (Censo Escolar, sinopses) costumam vir com ';' e latin-1.
    Tenta esse padrão primeiro e cai para utf-8/',' se falhar.
    """
    try:
        return pd.read_csv(caminho, sep=";", encoding="latin-1", dtype=str, low_memory=False)
    except (UnicodeDecodeError, pd.errors.ParserError):
        return pd.read_csv(caminho, sep=",", encoding="utf-8", dtype=str, low_memory=False)


def _ler_arquivo(caminho, abas_regex=None):
    sufixo = caminho.suffix.lower()
    if sufixo in (".xlsx", ".xls"):
        return _ler_planilha(caminho, abas_regex)
    if sufixo == ".csv":
        return _ler_csv(caminho)
    raise ValueError(f"Extensão não suportada: {caminho.name}")


def _extrair_ano(caminho, anos_esperados):
    """
    O ano do arquivo vem do NOME do arquivo (o INEP não costuma incluir uma
    coluna de ano dentro da planilha de uma única edição). Se o nome tiver
    zero ou mais de um ano plausível, o arquivo é pulado com aviso — melhor
    falhar visivelmente do que atribuir o ano errado a uma linha.
    """
    achados = {int(a) for a in ANO_REGEX.findall(caminho.name)}
    achados_validos = achados & set(anos_esperados)
    if len(achados_validos) == 1:
        return achados_validos.pop()
    return None


def _listar_candidatos(pasta, padroes):
    padroes_lower = [p.lower() for p in padroes]
    return [
        p for p in pasta.rglob("*")
        if p.is_file()
        and "_extraidos" not in p.relative_to(pasta).parts  # conteúdo de zip já tratado via o .zip
        and p.suffix.lower() in (".xlsx", ".xls", ".csv", ".zip")
        and all(pad in p.name.lower() for pad in padroes_lower)
    ]


def _extrair_zip(caminho_zip, pasta_destino):
    """Extrai um .zip do INEP para poder ler os arquivos internos (xlsx/csv)."""
    pasta_destino.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(caminho_zip) as z:
        nomes = [n for n in z.namelist() if not n.endswith("/")]
        z.extractall(pasta_destino)
    # os zips do INEP trazem também .ods (cópia do .xlsx), md5 .txt e Thumbs.db;
    # ~$ são arquivos de lock do Excel esquecidos dentro do zip
    return [pasta_destino / n for n in nomes
            if n.lower().endswith(EXTENSOES_DADOS) and not Path(n).name.startswith("~$")]


def _processar_fonte(nome_fonte, padroes, anos_esperados, abas_regex=None):
    candidatos = _listar_candidatos(RAW_EDU, padroes)

    arquivos = []
    for c in candidatos:
        if c.suffix.lower() == ".zip":
            arquivos.extend(_extrair_zip(c, RAW_EDU / "_extraidos" / c.stem))
        else:
            arquivos.append(c)

    if not arquivos:
        print(f"  [{nome_fonte}] nenhum arquivo encontrado em {RAW_EDU} "
              f"(padrões de nome: {padroes}) — pulando.")
        return None

    partes = []
    for caminho in tqdm(sorted(arquivos), desc=f"Lendo {nome_fonte}"):
        ano = _extrair_ano(caminho, anos_esperados)
        if ano is None:
            tqdm.write(f"  [{nome_fonte}] {caminho.name}: não achei um ano "
                       f"válido (esperado em {list(anos_esperados)}) no nome — pulando.")
            continue
        try:
            df = _ler_arquivo(caminho, abas_regex)
        except Exception as e:
            tqdm.write(f"  [{nome_fonte}] {caminho.name} falhou: {e}")
            continue
        df["_ano_arquivo"] = ano
        df["_arquivo_origem"] = caminho.name
        partes.append(df)

    if not partes:
        print(f"  [{nome_fonte}] nenhum arquivo lido com sucesso.")
        return None

    completo = pd.concat(partes, ignore_index=True)
    anos_lidos = sorted(completo["_ano_arquivo"].unique())
    faltando = sorted(set(anos_esperados) - set(anos_lidos))
    print(f"  [{nome_fonte}] {completo.shape[0]:,} linhas | anos lidos: {anos_lidos}"
          + (f" | FALTANDO: {faltando}" if faltando else ""))
    return completo


def main():
    print(f"Procurando arquivos brutos do INEP em: {RAW_EDU}\n")
    if not any(RAW_EDU.rglob("*")):
        print(f"  {RAW_EDU} está vazia. Baixe manualmente os arquivos do INEP "
              "(IDEB e Censo Escolar) e coloque-os aqui antes de rodar de novo.\n")

    for nome_fonte, cfg in FONTES_EDU.items():
        df = _processar_fonte(nome_fonte, cfg["padroes"], cfg["anos_esperados"], cfg.get("abas"))
        if df is not None:
            df.to_parquet(RAW / f"{nome_fonte}.parquet", index=False)
        del df

    print("\nExtração concluída. Arquivos crus (nacionais, ainda SEM filtro de UF) em:", RAW)


if __name__ == "__main__":
    main()
