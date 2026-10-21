"""Acumula candles de 5 min da watchlist em data/historico/5m/<ATIVO>/<AAAA-MM>.csv.

A brapi só entrega ~60 dias de intradiário; rodando todo dia (GitHub Actions), o histórico cresce sem limite.
Arquivos mensais em texto: o commit diário só altera o mês corrente e o git comprime bem.
"""
import os
import sys
import time
from pathlib import Path

import pandas as pd

from donchian_core import WATCHLIST_B3, carregar_brapi, HIST_DIR, COLS_HIST


def gravar(ticker, novo):
    pasta = HIST_DIR / ticker
    pasta.mkdir(parents=True, exist_ok=True)
    total = 0
    for mes, parte in novo.groupby(novo.index.strftime("%Y-%m")):
        arq = pasta / f"{mes}.csv"
        if arq.exists():
            antigo = pd.read_csv(arq, parse_dates=["Date"], index_col="Date")
            parte = pd.concat([antigo, parte])
        parte = parte[~parte.index.duplicated(keep="last")].sort_index()
        parte[COLS_HIST].to_csv(arq, float_format="%.4f")
        total += len(parte)
    return total


def main():
    token = os.environ["BRAPI_TOKEN"]
    agora = pd.Timestamp.now(tz="America/Sao_Paulo").tz_localize(None)
    ok = 0
    for t in WATCHLIST_B3:
        df = carregar_brapi(t, "3mo", token, "5m")
        if df.empty:
            print(f"{t}: sem dados")
            continue
        df = df[df.index + pd.Timedelta("5min") <= agora]          # sem o candle em formação
        if "Volume" not in df:
            df["Volume"] = 0
        n = gravar(t, df[COLS_HIST])
        ok += 1
        print(f"{t}: {len(df)} candles recebidos ({df.index[0]:%d/%m} → {df.index[-1]:%d/%m %H:%M}); meses tocados somam {n}")
        time.sleep(0.3)
    if not ok:
        sys.exit("Nenhum ativo coletado.")


if __name__ == "__main__":
    main()
