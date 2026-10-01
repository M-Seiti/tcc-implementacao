import pandas as pd
from tqdm.auto import tqdm

try:
    import nest_asyncio
    nest_asyncio.apply()
except Exception:
    pass

from pysus import sinasc, sim, cnes
from config import ESTADO, ANOS, CNES_MES_REF, RAW


def _baixar_anual(func, nome, **kwargs):
    partes, falhas = [], []
    for ano in tqdm(ANOS, desc=f"Baixando {nome} {ESTADO}"):
        try:
            df = func(state=ESTADO, year=ano, as_dataframe=True, **kwargs)
            if not isinstance(df, pd.DataFrame) or df.empty:
                raise RuntimeError("retorno vazio (ano indisponível no servidor)")
            df["_ano_arquivo"] = ano
            partes.append(df)
        except Exception as e:
            falhas.append((ano, str(e)))
            tqdm.write(f"  {nome} {ano} falhou: {e}")
    if not partes:
        raise RuntimeError(f"{nome}: nenhum ano baixado. Falhas: {falhas}")
    completo = pd.concat(partes, ignore_index=True)
    print(f"{nome}: {completo.shape[0]:,} linhas | anos ok: {len(partes)} | falhas: {falhas}")
    return completo


def main():
    df = _baixar_anual(sinasc, "SINASC")
    df.to_parquet(RAW / "sinasc_mg.parquet", index=False)
    del df

    df = _baixar_anual(sim, "SIM")
    df.to_parquet(RAW / "sim_mg.parquet", index=False)
    del df

    df = _baixar_anual(cnes, "CNES", month=CNES_MES_REF, group="ST")
    df.to_parquet(RAW / "cnes_mg.parquet", index=False)
    del df

    print("\nExtração concluída. Arquivos crus em:", RAW)


if __name__ == "__main__":
    main()
