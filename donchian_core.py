"""Lógica pura do scanner Donchian: dados, indicadores, zona de indecisão, rompimento e validação.

Sem dependência de Streamlit, para ser usada pelo app e pelo job do Kronos (GitHub Actions).
"""
import numpy as np
import pandas as pd
import requests

WATCHLIST_B3 = [
    "BOVA11", "PETR4", "VALE3", "ITUB4", "BBAS3",
    "BBDC4", "SANB11", "USIM5", "CSNA3", "WEGE3",
    "ABEV3", "RENT3", "SUZB3"
]

SINAL_C = "🟢 CRUZAMENTO COMPRA"
SINAL_V = "🔴 CRUZAMENTO VENDA"
ROMP_A = "🚀 ROMPIMENTO ALTA"
ROMP_B = "🩸 ROMPIMENTO BAIXA"

# Horizontes da validação, em candles de 5 minutos
HORIZONTES = {12: "1h", 48: "4h", 96: "~1 pregão"}   # rótulos em 5 min; use rotulo_h para outros intervalos
INTERVALOS = {"5m": 5, "15m": 15, "60m": 60}


def rotulo_h(h, minutos=5):
    """Duração de h candles: horas até 6h, senão pregões (~7h de pregão)."""
    t = h * minutos
    if t <= 360:
        return f"{t / 60:g}h"
    p = t / 420
    return "~1 pregão" if p < 1.5 else f"~{p:.1f} pregões".replace(".", ",")


def carregar_brapi(ticker, range_val, token, interval="5m"):
    """Candles da brapi com colunas Open/High/Low/Close/Volume e índice Date (horário de Brasília)."""
    url = f"https://brapi.dev/api/quote/{ticker}?range={range_val}&interval={interval}"
    try:
        resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30).json()
        hist = (resp.get("results") or [{}])[0].get("historicalDataPrice", [])
        df = pd.DataFrame(hist)
        if df.empty:
            return df
        df["Date"] = pd.to_datetime(df["date"], unit="s", utc=True).dt.tz_convert("America/Sao_Paulo").dt.tz_localize(None)
        df = df.rename(columns={"open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
        n_bruto = len(df)
        n_nulos = int(df[["Open", "High", "Low", "Close"]].isna().any(axis=1).sum())
        df = df.dropna(subset=["Open", "High", "Low", "Close"])
        n_dup = int(df.duplicated("Date").sum())
        df = df.drop_duplicates("Date").sort_values("Date").set_index("Date")
        df.attrs.update(n_bruto=n_bruto, n_nulos=n_nulos, n_duplicados=n_dup)
        return df
    except Exception:
        return pd.DataFrame()


def atr(df, n=14):
    pc = df["Close"].shift(1)
    tr = pd.concat([df["High"] - df["Low"], (df["High"] - pc).abs(), (df["Low"] - pc).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()


def _primeiro(mask):
    """Mantém só o primeiro candle de cada sequência True."""
    mask = mask.fillna(False).astype(bool)
    return mask & ~mask.shift(1, fill_value=False)


def processar_indicadores(df, limiar_zona=0.08, limiar_romp=0.20, janela_zona=60, janela_incl=10):
    if len(df) < 610:
        return None
    df = df.copy()

    df['MA_500'] = df['Close'].rolling(window=500).mean()
    df['MA_610'] = df['Close'].rolling(window=610).mean()

    df['Donchian_Upper'] = df['High'].rolling(window=305).max()
    df['Donchian_Lower'] = df['Low'].rolling(window=305).min()
    df['Donchian_Mid'] = (df['Donchian_Upper'] + df['Donchian_Lower']) / 2

    df['Upper_Slope'] = df['Donchian_Upper'].diff(janela_incl)
    df['Lower_Slope'] = df['Donchian_Lower'].diff(janela_incl)

    df['Estado_Canal'] = "Lateral / Compressão ⚖️"
    exp_alta = (df['Upper_Slope'] > 0) & (df['Lower_Slope'] > 0)
    exp_baixa = (df['Upper_Slope'] < 0) & (df['Lower_Slope'] < 0)
    alargamento = (df['Upper_Slope'] > 0) & (df['Lower_Slope'] < 0)
    estreitamento = (df['Upper_Slope'] < 0) & (df['Lower_Slope'] > 0)

    df.loc[exp_alta, 'Estado_Canal'] = "📈 Expansão de Alta"
    df.loc[exp_baixa, 'Estado_Canal'] = "📉 Expansão de Baixa"
    df.loc[alargamento, 'Estado_Canal'] = "🌊 Alargamento"
    df.loc[estreitamento, 'Estado_Canal'] = "🤏 Squeeze"

    df['Sinal'] = "Aguardar"
    df['Alerta_Fundo'] = ""
    df['Alerta_Topo'] = ""

    donch_mid_prev = df['Donchian_Mid'].shift(3)
    ma_500_prev = df['MA_500'].shift(3)

    compra_mask = (df['Donchian_Mid'] > df['MA_500']) & (donch_mid_prev <= ma_500_prev)
    venda_mask = (df['Donchian_Mid'] < df['MA_500']) & (donch_mid_prev >= ma_500_prev)
    # o shift(3) repetia o mesmo cruzamento em até 3 candles seguidos: fica só o primeiro
    df.loc[_primeiro(compra_mask), 'Sinal'] = SINAL_C
    df.loc[_primeiro(venda_mask), 'Sinal'] = SINAL_V

    alerta_fundo_mask = (df['Low'] <= df['Donchian_Lower']) & (df['Close'] < df['MA_500'])
    df.loc[alerta_fundo_mask, 'Alerta_Fundo'] = "⚠️ Tocou Fundo / Exaustão"

    alerta_topo_mask = (df['High'] >= df['Donchian_Upper']) & (df['Close'] > df['MA_500'])
    df.loc[alerta_topo_mask, 'Alerta_Topo'] = "🎯 Tocou Topo / Alvo"

    # --- Zona de indecisão (Mid colado na MA500) e rompimento ---
    largura = (df['Donchian_Upper'] - df['Donchian_Lower']).replace(0, np.nan)
    df['Dist_Rel'] = (df['Donchian_Mid'] - df['MA_500']) / largura   # fração da largura do canal
    dist_abs = df['Dist_Rel'].abs()
    df['Zona_Indecisao'] = dist_abs < limiar_zona

    lado = np.sign(df['Donchian_Mid'] - df['MA_500'])
    cruz = (lado != lado.shift()) & lado.notna() & lado.shift().notna()
    df['Cruz_Janela'] = cruz.astype(float).rolling(janela_zona, min_periods=1).sum()

    esteve_na_zona = (df['Zona_Indecisao'].astype(float)
                      .rolling(janela_zona, min_periods=1).max().shift(1).fillna(0).astype(bool))
    saida = _primeiro(dist_abs >= limiar_romp) & esteve_na_zona
    df['Rompimento'] = ""
    df.loc[saida & (df['Dist_Rel'] > 0), 'Rompimento'] = ROMP_A
    df.loc[saida & (df['Dist_Rel'] < 0), 'Rompimento'] = ROMP_B
    return df


def status_zona(df, janela_zona=60):
    """Texto curto com a situação atual: na zona, rompeu recentemente, ou nada."""
    ult = df.iloc[-1]
    if ult['Zona_Indecisao']:
        return f"⚖️ Na zona ({int(ult['Cruz_Janela'])} cruz.)"
    idx = np.flatnonzero(df['Rompimento'].values != "")
    if len(idx) and len(df) - 1 - idx[-1] <= janela_zona:
        return f"{df['Rompimento'].iloc[idx[-1]]} há {len(df) - 1 - idx[-1]} candles"
    return "—"


def _eventos(df):
    return {
        "🟢 Cruzamento compra": (df['Sinal'] == SINAL_C, 1),
        "🔴 Cruzamento venda": (df['Sinal'] == SINAL_V, -1),
        "🚀 Rompimento alta": (df['Rompimento'] == ROMP_A, 1),
        "🩸 Rompimento baixa": (df['Rompimento'] == ROMP_B, -1),
        "🎯 Toque topo (segue alta?)": (_primeiro(df['Alerta_Topo'] != ""), 1),
        "⚠️ Toque fundo (segue baixa?)": (_primeiro(df['Alerta_Fundo'] != ""), -1),
    }


def resultados_eventos(df, horizontes=HORIZONTES, ticker=""):
    """O que aconteceu depois de cada evento, e o mesmo para uma entrada aleatória (baseline).

    Retorna (ev, base):
      ev   — uma linha por evento × horizonte: retorno no sentido do sinal, MFE e MAE (%)
      base — somas por sentido × horizonte considerando TODOS os candles (para média ponderada)
    """
    C = pd.Series(df['Close'].values)
    H = pd.Series(df['High'].values)
    L = pd.Series(df['Low'].values)
    aquecido = df['MA_610'].notna().values
    eventos = {k: (m.values, d) for k, (m, d) in _eventos(df).items()}
    ev, base = [], []
    for hz in horizontes:
        ret = (C.shift(-hz) / C - 1).values * 100
        fmax = (H.shift(-1).iloc[::-1].rolling(hz).max().iloc[::-1] / C - 1).values * 100
        fmin = (L.shift(-1).iloc[::-1].rolling(hz).min().iloc[::-1] / C - 1).values * 100
        ok = aquecido & ~np.isnan(ret) & ~np.isnan(fmax)
        for d in (1, -1):
            r, mfe, mae = (ret, fmax, fmin) if d == 1 else (-ret, -fmin, -fmax)
            base.append(dict(dir=d, h=hz, n=ok.sum(), s_ret=r[ok].sum(), s_mfe=mfe[ok].sum(),
                             s_hit=(r[ok] > 0).sum()))
            for nome, (mask, dd) in eventos.items():
                if dd != d:
                    continue
                sel = mask & ok
                for i in np.flatnonzero(sel):
                    ev.append(dict(ticker=ticker, evento=nome, dir=d, h=hz, data=df.index[i],
                                   ret=r[i], mfe=mfe[i], mae=mae[i]))
    cols = ["ticker", "evento", "dir", "h", "data", "ret", "mfe", "mae"]
    return pd.DataFrame(ev, columns=cols), pd.DataFrame(base)


def resumir_validacao(ev, base, minutos=5):
    """Tabela por evento × horizonte comparada à entrada aleatória no mesmo sentido."""
    if ev.empty:
        return pd.DataFrame()
    b = base.groupby(["dir", "h"]).sum(numeric_only=True)
    b = pd.DataFrame({"ale_ret": b.s_ret / b.n, "ale_mfe": b.s_mfe / b.n, "ale_hit": b.s_hit / b.n * 100})
    g = ev.groupby(["evento", "dir", "h"]).agg(
        N=("ret", "size"), acerto=("ret", lambda x: (x > 0).mean() * 100),
        ret=("ret", "mean"), mfe=("mfe", "mean"), mae=("mae", "mean")).reset_index()
    g = g.join(b, on=["dir", "h"])
    ordem = list(_eventos(pd.DataFrame(columns=['Sinal', 'Rompimento', 'Alerta_Topo', 'Alerta_Fundo'])).keys())
    g["_o"] = g.evento.map({k: i for i, k in enumerate(ordem)})
    g = g.sort_values(["h", "_o"])
    return pd.DataFrame({
        "Evento": g.evento,
        "Horizonte": g.h.map(lambda h: f"{h} candles ({rotulo_h(h, minutos)})"),
        "h": g.h,
        "N": g.N,
        "Acerto (%)": g.acerto.round(0),
        "Acerto aleatório (%)": g.ale_hit.round(0),
        "Retorno médio (%)": g.ret.round(2),
        "Retorno aleatório (%)": g.ale_ret.round(2),
        "Vantagem (p.p.)": (g.ret - g.ale_ret).round(2),
        "Mov. máx. a favor (%)": g.mfe.round(2),
        "Mov. máx. aleatório (%)": g.ale_mfe.round(2),
        "Mov. máx. contra (%)": g.mae.round(2),
    }).reset_index(drop=True)
