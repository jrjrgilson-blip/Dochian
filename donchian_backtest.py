"""Backtest por operação, sem alvo: entra no sinal e deixa correr até a regra de saída.

Execução realista: o sinal é lido no fecho do candle i e executado na abertura de i+1.
Stop (opcional) em múltiplos do ATR da entrada, verificado dentro do candle; com gap, sai na abertura.
"""
import numpy as np
import pandas as pd

from donchian_core import SINAL_C, SINAL_V, ROMP_A, ROMP_B, atr

ESTRATEGIAS = {
    "rompimento": "🚀 Rompimento (sai ao voltar à zona)",
    "cruzamento": "🔁 Todo cruzamento (sempre posicionado)",
}


def backtest(df, estrategia="rompimento", limiar_zona=0.08, stop_atr=0.0, custo_lado=0.03, sentido="ambos"):
    d = df[df["MA_610"].notna()]
    if len(d) < 3:
        return pd.DataFrame()
    o, h, l, c = (d[k].values for k in ("Open", "High", "Low", "Close"))
    dist = d["Dist_Rel"].values
    a = atr(df).reindex(d.index).values
    if estrategia == "rompimento":
        sinal = np.where(d["Rompimento"] == ROMP_A, 1, np.where(d["Rompimento"] == ROMP_B, -1, 0))
    else:
        sinal = np.where(d["Sinal"] == SINAL_C, 1, np.where(d["Sinal"] == SINAL_V, -1, 0))
    pode = (lambda s: s == 1) if sentido == "compra" else (lambda s: s != 0)

    ops, pos, n = [], 0, len(d)
    ent_i = ent_px = stop_px = 0

    def fechar(i_saida, px, motivo):
        nonlocal pos
        hi, lo = h[ent_i:i_saida + 1].max(), l[ent_i:i_saida + 1].min()
        bruto = pos * (px / ent_px - 1) * 100
        ops.append(dict(Entrada=d.index[ent_i], Saída=d.index[i_saida], Lado="Compra" if pos == 1 else "Venda",
                        **{"Preço entrada": ent_px, "Preço saída": px},
                        **{"Resultado (%)": bruto - 2 * custo_lado, "Candles": i_saida - ent_i,
                           "Mov. máx. a favor (%)": ((hi / ent_px - 1) if pos == 1 else (1 - lo / ent_px)) * 100,
                           "Mov. máx. contra (%)": ((lo / ent_px - 1) if pos == 1 else (1 - hi / ent_px)) * 100,
                           "Motivo": motivo}))
        pos = 0

    for i in range(n):
        if pos != 0 and i >= ent_i and stop_atr > 0:
            if pos == 1 and l[i] <= stop_px:
                fechar(i, min(o[i], stop_px) if i > ent_i else stop_px, "🛑 Stop")
            elif pos == -1 and h[i] >= stop_px:
                fechar(i, max(o[i], stop_px) if i > ent_i else stop_px, "🛑 Stop")
        if pos != 0 and i + 1 < n:
            if estrategia == "rompimento":
                motivo = "↩️ Voltou à zona" if abs(dist[i]) < limiar_zona else ("🔄 Rompimento contrário" if sinal[i] == -pos else "")
            else:
                motivo = "🔄 Cruzamento contrário" if sinal[i] == -pos else ""
            if motivo:
                fechar(i + 1, o[i + 1], motivo)
        if pos == 0 and sinal[i] != 0 and pode(sinal[i]) and i + 1 < n:
            pos, ent_i, ent_px = int(sinal[i]), i + 1, o[i + 1]
            stop_px = ent_px - pos * stop_atr * (a[i] if np.isfinite(a[i]) else 0)
    if pos != 0:
        fechar(n - 1, c[-1], "⏳ Em aberto")
    return pd.DataFrame(ops)


def resumo(ops, nome=""):
    if ops is None or ops.empty:
        return {"Estratégia": nome, "Operações": 0}
    r = ops["Resultado (%)"]
    g, p = r[r > 0], r[r <= 0]
    curva = (1 + r / 100).cumprod()
    dd = (curva / curva.cummax() - 1).min() * 100
    return {
        "Estratégia": nome,
        "Operações": len(r),
        "Acerto (%)": round((r > 0).mean() * 100, 0),
        "Ganho médio (%)": round(g.mean(), 2) if len(g) else 0.0,
        "Perda média (%)": round(p.mean(), 2) if len(p) else 0.0,
        "Payoff": round(g.mean() / -p.mean(), 2) if len(g) and len(p) and p.mean() < 0 else np.nan,
        "Fator de lucro": round(g.sum() / -p.sum(), 2) if len(p) and p.sum() < 0 else np.nan,
        "Expectativa por op. (%)": round(r.mean(), 2),
        "Resultado composto (%)": round((curva.iloc[-1] - 1) * 100, 2),
        "Maior perda (%)": round(r.min(), 2),
        "Drawdown máx. (%)": round(dd, 2),
        "Duração média (candles)": round(ops["Candles"].mean(), 0),
        "Stops": int((ops["Motivo"] == "🛑 Stop").sum()),
    }


def curva_capital(ops):
    if ops is None or ops.empty:
        return pd.Series(dtype=float)
    s = (1 + ops["Resultado (%)"] / 100).cumprod().mul(100) - 100
    s.index = ops["Saída"]
    return s
