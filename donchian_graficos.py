"""Gráficos Plotly do scanner Donchian."""
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from donchian_core import SINAL_C, SINAL_V, ROMP_A, ROMP_B

COR = dict(alta="#26a69a", baixa="#ef5350", mid="#ff9800", ma500="#2962ff", ma610="#ab47bc",
           canal="rgba(120,144,156,0.6)", zona="rgba(255,193,7,0.13)", kronos="#00bcd4")


def _rangebreaks(idx):
    """Esconde noites e fins de semana para os candles de 5m ficarem colados."""
    t = idx.hour + idx.minute / 60
    ini, fim = float(t.min()), float(t.max()) + 5 / 60
    rb = [dict(bounds=["sat", "mon"])]
    if fim - ini < 23:
        rb.append(dict(bounds=[fim, ini], pattern="hour"))
    return rb


def _faixas(mask):
    """Intervalos contínuos (início, fim) onde mask é True."""
    grupos = (mask != mask.shift()).cumsum()
    return [(g.index[0], g.index[-1]) for _, g in mask[mask].groupby(grupos[mask])]


def grafico_ativo(df, n_candles, limiar_zona, limiar_romp, previsao=None, titulo=""):
    d = df.tail(n_candles)
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.74, 0.26], vertical_spacing=0.03,
                        subplot_titles=(titulo, "Distância Mid × MA500 (fração da largura do canal)"))

    fig.add_trace(go.Candlestick(x=d.index, open=d.Open, high=d.High, low=d.Low, close=d.Close, name="Preço",
                                 increasing_line_color=COR["alta"], decreasing_line_color=COR["baixa"],
                                 showlegend=False), 1, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d.Donchian_Upper, name="Donchian 305", line=dict(color=COR["canal"], width=1)), 1, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d.Donchian_Lower, name="Donchian inf.", line=dict(color=COR["canal"], width=1),
                             fill="tonexty", fillcolor="rgba(120,144,156,0.07)", showlegend=False), 1, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d.Donchian_Mid, name="Mid", line=dict(color=COR["mid"], width=2)), 1, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d.MA_500, name="MA 500", line=dict(color=COR["ma500"], width=2)), 1, 1)
    fig.add_trace(go.Scatter(x=d.index, y=d.MA_610, name="MA 610", line=dict(color=COR["ma610"], width=1.5, dash="dash")), 1, 1)

    marcadores = [
        (d.Sinal == SINAL_C, d.Low * 0.998, "triangle-up", COR["alta"], 11, "Cruz. compra"),
        (d.Sinal == SINAL_V, d.High * 1.002, "triangle-down", COR["baixa"], 11, "Cruz. venda"),
        (d.Rompimento == ROMP_A, d.Low * 0.996, "star", COR["alta"], 17, "Rompimento alta"),
        (d.Rompimento == ROMP_B, d.High * 1.004, "star", COR["baixa"], 17, "Rompimento baixa"),
    ]
    for m, y, simb, cor, tam, nome in marcadores:
        if m.any():
            fig.add_trace(go.Scatter(x=d.index[m], y=y[m], mode="markers", name=nome,
                                     marker=dict(symbol=simb, color=cor, size=tam, line=dict(color="white", width=1))), 1, 1)

    if previsao is not None and not previsao.empty:
        p = previsao.sort_values("timestamps")
        x = pd.concat([pd.Series([d.index[-1]]), p.timestamps])
        ini = pd.Series([d.Close.iloc[-1]])
        fig.add_trace(go.Scatter(x=x, y=pd.concat([ini, p.p90]), line=dict(width=0), showlegend=False, hoverinfo="skip"), 1, 1)
        fig.add_trace(go.Scatter(x=x, y=pd.concat([ini, p.p10]), line=dict(width=0), fill="tonexty",
                                 fillcolor="rgba(0,188,212,0.18)", name="Kronos P10–P90"), 1, 1)
        fig.add_trace(go.Scatter(x=x, y=pd.concat([ini, p.med]), name="Kronos (mediana)",
                                 line=dict(color=COR["kronos"], width=2, dash="dot")), 1, 1)

    fig.add_trace(go.Scatter(x=d.index, y=d.Dist_Rel, name="Distância", line=dict(color=COR["mid"], width=1.5),
                             showlegend=False), 2, 1)
    for v, estilo in [(limiar_zona, "dash"), (-limiar_zona, "dash"), (limiar_romp, "dot"), (-limiar_romp, "dot")]:
        fig.add_hline(y=v, line=dict(color="gray", width=1, dash=estilo), row=2, col=1)
    fig.add_hline(y=0, line=dict(color=COR["ma500"], width=1), row=2, col=1)

    for x0, x1 in _faixas(d.Zona_Indecisao.fillna(False))[-150:]:
        fig.add_vrect(x0=x0, x1=x1, fillcolor=COR["zona"], line_width=0, layer="below", row="all", col=1)

    fig.update_xaxes(rangebreaks=_rangebreaks(d.index), rangeslider_visible=False)
    fig.update_layout(height=760, margin=dict(l=10, r=10, t=40, b=10), hovermode="x unified",
                      legend=dict(orientation="h", y=1.06, x=0, font=dict(size=11)), dragmode="pan")
    return fig


def grafico_validacao(res, h):
    r = res[res.h == h]
    fig = make_subplots(rows=2, cols=1, vertical_spacing=0.18,
                        subplot_titles=("Retorno médio no sentido do sinal (%)", "Movimento máximo a favor (%)"))
    for col, nome, cor, row in [("Retorno médio (%)", "Evento", "#2962ff", 1), ("Retorno aleatório (%)", "Aleatório", "#9e9e9e", 1),
                                ("Mov. máx. a favor (%)", "Evento", "#2962ff", 2), ("Mov. máx. aleatório (%)", "Aleatório", "#9e9e9e", 2)]:
        fig.add_trace(go.Bar(x=r.Evento, y=r[col], name=nome, marker_color=cor, showlegend=row == 1,
                             text=r[col].map(lambda v: f"{v:.2f}"), textposition="outside",
                             customdata=r.N, hovertemplate="%{x}<br>%{y:.2f}% (N=%{customdata})<extra></extra>"), row, 1)
    fig.update_layout(barmode="group", height=560, margin=dict(l=10, r=10, t=40, b=10),
                      legend=dict(orientation="h", y=1.08, x=0))
    return fig
