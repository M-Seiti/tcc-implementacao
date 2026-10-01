from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
RAW = DATA_DIR / "raw"
INTERIM = DATA_DIR / "interim"
PROCESSED = DATA_DIR / "processed"
FIGURES = BASE_DIR / "reports" / "figures"
QUALIDADE = BASE_DIR / "reports" / "qualidade"

for _p in (RAW, INTERIM, PROCESSED, FIGURES, QUALIDADE):
    _p.mkdir(parents=True, exist_ok=True)

ESTADO = "MG"
ANOS = range(2010, 2020)
CNES_MES_REF = 12
N_MUNICIPIOS_MG = 853

COLS_SINASC = ["CODMUNRES", "DTNASC", "IDADEMAE", "ESCMAE",
               "PESO", "CONSULTAS", "PARTO"]

COLS_SIM = ["CODMUNRES", "DTOBITO", "DTNASC", "TIPOBITO", "CAUSABAS"]

COLS_CNES = ["CNES", "CODUFMUN", "TPGESTAO", "TP_UNID"]

IGNORADO_SINASC = {"ESCMAE": ["9", "0", ""],
                   "CONSULTAS": ["9", ""],
                   "PARTO": ["9", ""]}

# ---------------------------------------------------------------------------
# EDUCAÇÃO (INEP) — não existe biblioteca de download tipo PySUS para o INEP;
# os arquivos são baixados manualmente do portal e colocados em RAW_EDU antes
# de rodar `python extract_edu.py`.
# ---------------------------------------------------------------------------
RAW_EDU = RAW / "edu"
RAW_EDU.mkdir(parents=True, exist_ok=True)

ANOS_CENSO = range(2010, 2020)              # Censo Escolar: anual
ANOS_IDEB = [2011, 2013, 2015, 2017, 2019]  # IDEB: BIENAL — não existe em anos pares

# Cada fonte é identificada pelo NOME do arquivo (busca por substring, case-
# insensitive, todas as palavras da lista precisam aparecer no nome). Ajuste
# aqui se os arquivos baixados do INEP tiverem nomes diferentes destes.
#
# "abas" (opcional): regex do nome das abas a ler; sem ela, lê todas as abas
# que tiverem linhas de município (os arquivos de 2010/2011 vêm quebrados em
# abas por região).
#
# IDEB: usamos só o arquivo de divulgação de 2019, que já traz a série
# histórica inteira em colunas (VL_OBSERVADO_2005 ... VL_OBSERVADO_2019) —
# transform_edu.py passa isso para o formato longo (município-ano).
FONTES_EDU = {
    "ideb_iniciais": {"padroes": ["ideb", "inicia"], "anos_esperados": [2019]},
    "ideb_finais":   {"padroes": ["ideb", "finai"],   "anos_esperados": [2019]},
    # Sinopse tem ~170 abas; "Educação Básica 1.1" = nº de matrículas da
    # educação básica por município (mesmo layout em 2010–2019).
    "matriculas":    {"padroes": ["sinopse"],          "anos_esperados": ANOS_CENSO,
                      "abas": r"Educa.*1\.1$"},
    "distorcao":     {"padroes": ["distor"],           "anos_esperados": ANOS_CENSO},
    "rendimento":    {"padroes": ["rendimento"],       "anos_esperados": ANOS_CENSO},
}

# Planilhas do INEP têm título + cabeçalho de 2 a 4 linhas mescladas antes dos
# dados. O início do cabeçalho é a linha com uma célula EXATAMENTE igual a um
# destes nomes (comparação sem acento/espaço/underscore) — não basta conter
# "MUNICIPIO", porque o título da planilha também contém.
MARCADORES_CABECALHO_EDU = ["CODIGO DO MUNICIPIO", "CO_MUNICIPIO", "PK_COD_MUNICIPIO", "COD_MUNICIPIO"]

# Nomes candidatos (após normalizar para maiúsculo, sem acento) para as
# colunas-chave. O nome exato MUDA entre edições do INEP — por isso a busca
# é por uma lista de candidatos, não por um nome fixo.
COLS_CANDIDATAS_COD_MUNICIPIO = [
    "CO_MUNICIPIO", "COD_MUNICIPIO", "CODIGO_MUNICIPIO", "CODIGO DO MUNICIPIO",
    "CO_MUN", "ID_MUNICIPIO", "COD_MUN", "PK_COD_MUNICIPIO",
]
COLS_CANDIDATAS_NOME_MUNICIPIO = [
    "NO_MUNICIPIO", "MUNICIPIO", "NOME_MUNICIPIO", "NOME DO MUNICIPIO",
]
COLS_CANDIDATAS_UF = ["SG_UF", "UF", "CO_UF", "SIGLA_UF"]

# Distorção e rendimento vêm com uma linha por município x localização
# (Total/Urbana/Rural) x rede (Total/Pública/Estadual/Municipal/Privada/
# Federal). Usamos só a linha Total x Total (todas as escolas do município);
# fazer média entre as quebras misturaria subtotais com o total.
COLS_CANDIDATAS_LOCALIZACAO = ["LOCALIZACAO", "TIPOLOCA", "NO_CATEGORIA"]
COLS_CANDIDATAS_REDE = ["REDE", "DEPENDAD", "NO_DEPENDENCIA", "DEPENDENCIA ADMINISTRATIVA"]
LOCALIZACAO_EDU = "Total"
REDE_EDU = "Total"
# O arquivo de IDEB por município não tem rede "Total" (só Estadual,
# Municipal e Pública) — a rede pública é o recorte usual do IDEB municipal.
REDE_IDEB = "Pública"

# Sentinelas de "ignorado"/"não aplicável"/"não divulgado" mais comuns em
# planilhas do INEP. ATENÇÃO (regra aprendida com a saúde): isto é um ponto
# de partida — confira campo a campo contra os arquivos reais antes de usar,
# o sentinela varia (ex.: "-" pode ser 0 de verdade em algumas colunas e
# "não aplicável" em outras). Ajustar em transform_edu.py conforme necessário.
IGNORADO_EDU_PADRAO = ["-", "--", "ND", "N/D", "*", "#VALOR!", ""]
