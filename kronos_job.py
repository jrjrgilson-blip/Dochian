"""Roda o Kronos na watchlist e grava data/kronos_sinais.csv e data/kronos_previsao.csv.

Executado diariamente pelo GitHub Actions (.github/workflows/kronos.yml); o app só lê os CSVs.
Variáveis: BRAPI_TOKEN (obrigatória), KRONOS_DIR, PRED_LEN, N_CAMINHOS, LOOKBACK.
"""
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from donchian_core import WATCHLIST_B3, atr, carregar_brapi, processar_indicadores

PRED_LEN = int(os.environ.get("PRED_LEN", 24))      # 24 candles de 5m = 2h
N_CAMINHOS = int(os.environ.get("N_CAMINHOS", 10))
LOOKBACK = int(os.environ.get("LOOKBACK", 400))     # máx. 512
MODELO, TOKENIZER = "NeoQuasar/Kronos-small", "NeoQuasar/Kronos-Tokenizer-base"
SAIDA = Path(__file__).parent / "data"


def proximos_timestamps(ts, n):
    """Próximos n horários de pregão, com o passo e o horário observados nos próprios dados."""
    ts = pd.Series(ts).reset_index(drop=True)
    passo = ts.diff().mode().iloc[0]
    ini, fim = ts.dt.time.min(), ts.dt.time.max()
    out, t = [], ts.iloc[-1]
    while len(out) < n:
        t += passo
        if t.weekday() >= 5 or t.time() > fim:
            t = t.normalize() + pd.Timedelta("1D") + pd.Timedelta(hours=ini.hour, minutes=ini.minute) - passo
            continue
        if t.time() >= ini:
            out.append(t)
    return pd.Series(out)


def carregar_predictor():
    import torch
    sys.path.insert(0, os.environ.get("KRONOS_DIR", "kronos_src"))
    from model import Kronos, KronosPredictor, KronosTokenizer
    torch.set_num_threads(os.cpu_count() or 2)
    return KronosPredictor(Kronos.from_pretrained(MODELO), KronosTokenizer.from_pretrained(TOKENIZER),
                           device="cpu", max_context=512)


def prever_ativo(predictor, ticker, df, gerado_em):
    ind = processar_indicadores(df)
    hist = df.tail(LOOKBACK)
    x = hist.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]].reset_index(drop=True)
    x["volume"] = x["volume"].fillna(0).astype(float)
    x_ts = pd.Series(hist.index)
    y_ts = proximos_timestamps(x_ts, PRED_LEN)

    # cada cópia com sample_count=1 gera um caminho independente
    out = predictor.predict_batch(df_list=[x] * N_CAMINHOS, x_timestamp_list=[x_ts] * N_CAMINHOS,
                                  y_timestamp_list=[y_ts] * N_CAMINHOS, pred_len=PRED_LEN,
                                  T=1.0, top_p=0.9, sample_count=1, verbose=False)
    close = np.stack([o["close"].values for o in out])
    high = np.stack([o["high"].values for o in out])
    low = np.stack([o["low"].values for o in out])

    ult = float(hist["Close"].iloc[-1])
    a = float(atr(hist).iloc[-1])
    amp = float(np.clip(high - low, 0, None).mean())
    sup = ind["Donchian_Upper"].iloc[-1] if ind is not None else np.nan
    inf = ind["Donchian_Lower"].iloc[-1] if ind is not None else np.nan

    sinal = dict(ticker=ticker, gerado_em=gerado_em, ultimo_candle=hist.index[-1], close=ult,
                 med_final=float(np.median(close[:, -1])),
                 p10_final=float(np.percentile(close[:, -1], 10)),
                 p90_final=float(np.percentile(close[:, -1], 90)),
                 amp_prevista=amp, atr=a, razao_amp_atr=amp / a if a > 0 else np.nan,
                 prob_alta=float((close[:, -1] > ult).mean()),
                 prob_rompe_topo=float((high.max(axis=1) > sup).mean()),
                 prob_rompe_fundo=float((low.min(axis=1) < inf).mean()),
                 pred_len=PRED_LEN)
    prev = pd.DataFrame(dict(ticker=ticker, timestamps=y_ts.values, med=np.median(close, axis=0),
                             p10=np.percentile(close, 10, axis=0), p90=np.percentile(close, 90, axis=0)))
    return sinal, prev


def main(predictor=None):
    token = os.environ["BRAPI_TOKEN"]
    predictor = predictor or carregar_predictor()
    gerado_em = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M")
    sinais, prevs = [], []
    for ticker in WATCHLIST_B3:
        t0 = time.time()
        df = carregar_brapi(ticker, "1mo", token)
        if len(df) < LOOKBACK + 20:
            print(f"{ticker}: dados insuficientes ({len(df)} candles), pulando")
            continue
        try:
            s, p = prever_ativo(predictor, ticker, df, gerado_em)
        except Exception as e:
            print(f"{ticker}: erro {e!r}")
            continue
        sinais.append(s)
        prevs.append(p)
        print(f"{ticker}: razão amp/ATR {s['razao_amp_atr']:.2f}, prob. alta {s['prob_alta']:.0%} ({time.time() - t0:.0f}s)")

    if not sinais:
        sys.exit("Nenhum ativo processado — CSVs anteriores mantidos.")
    SAIDA.mkdir(exist_ok=True)
    sinais_df, prev_df = pd.DataFrame(sinais), pd.concat(prevs)
    sinais_df = sinais_df.round({c: 4 for c in sinais_df.select_dtypes("number").columns})
    prev_df = prev_df.round({"med": 2, "p10": 2, "p90": 2})
    sinais_df.to_csv(SAIDA / "kronos_sinais.csv", index=False)
    prev_df.to_csv(SAIDA / "kronos_previsao.csv", index=False)
    print(f"OK: {len(sinais)} ativos gravados em {SAIDA}")


if __name__ == "__main__":
    main()
