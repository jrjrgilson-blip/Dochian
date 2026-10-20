"""Relatório de coerência (HTML autocontido) para um ativo, gerado sob demanda no app."""
import html
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from donchian_core import SINAL_C, SINAL_V, ROMP_A, ROMP_B, HORIZONTES, status_zona

OK, ATENCAO, FALHA = "✅", "⚠️", "❌"
WHIPSAW_CANDLES = 24   # cruzamento desfeito em até 2h = sinal falso (whipsaw)


def _chk(lista, nivel, item, detalhe):
    lista.append({"": nivel, "Verificação": item, "Detalhe": detalhe})


def _alinhamento(r):
    if r.Donchian_Mid > r.MA_500 > r.MA_610:
        return "🟢 Altista Perfeito"
    if r.Donchian_Mid < r.MA_500 < r.MA_610:
        return "🔴 Baixista Perfeito"
    return "⚖️ Transição"


# ------------------------------------------------------------------ dados
def checar_dados(df):
    c, a = [], df.attrs
    passo = df.index.to_series().diff()
    passo_tip = passo.mode().iloc[0] if len(passo.dropna()) else pd.Timedelta("5min")
    dias = df.index.normalize().nunique()
    por_dia = df.groupby(df.index.normalize()).size()
    esperado = int(por_dia.quantile(0.9))
    dias_incompletos = por_dia[por_dia < esperado * 0.8]

    _chk(c, OK, "Volume de dados", f"{len(df)} candles em {dias} pregões ({df.index[0]:%d/%m/%Y} → {df.index[-1]:%d/%m/%Y %H:%M}); "
         f"intervalo típico {int(passo_tip.total_seconds() // 60)} min, ~{esperado} candles/pregão")

    nb, nn, nd = a.get("n_bruto"), a.get("n_nulos", 0), a.get("n_duplicados", 0)
    if nb is not None:
        _chk(c, OK if nn + nd == 0 else ATENCAO, "Linhas descartadas na carga",
             f"{nn} com preço nulo e {nd} horários duplicados, de {nb} recebidos da brapi")

    mesmo_dia = passo[(df.index.to_series().dt.normalize().diff() == pd.Timedelta(0))]
    buracos = mesmo_dia[mesmo_dia > passo_tip * 1.5]
    faltam = int((buracos / passo_tip - 1).round().sum()) if len(buracos) else 0
    _chk(c, OK if len(buracos) == 0 else (ATENCAO if faltam < 0.02 * len(df) else FALHA),
         "Buracos dentro do pregão", f"{len(buracos)} intervalos sem dados (~{faltam} candles faltando)")
    _chk(c, OK if dias_incompletos.empty else ATENCAO, "Pregões incompletos",
         "nenhum" if dias_incompletos.empty else
         ", ".join(f"{d:%d/%m} ({n})" for d, n in dias_incompletos.tail(10).items()) + " — pode ser feriado/meio-pregão")

    o, h, l, cl = df.Open, df.High, df.Low, df.Close
    incons = (h < np.maximum(o, cl) - 1e-9) | (l > np.minimum(o, cl) + 1e-9) | (h < l)
    _chk(c, OK if not incons.any() else FALHA, "Consistência OHLC (mín ≤ abertura/fecho ≤ máx)",
         f"{int(incons.sum())} candles inconsistentes" + (f" — ex.: {', '.join(f'{t:%d/%m %H:%M}' for t in df.index[incons][:5])}" if incons.any() else ""))
    nao_pos = (df[["Open", "High", "Low", "Close"]] <= 0).any(axis=1)
    if nao_pos.any():
        _chk(c, FALHA, "Preços ≤ 0", f"{int(nao_pos.sum())} candles")

    vol = df.get("Volume", pd.Series(np.nan, index=df.index))
    vol0 = int((vol.fillna(0) <= 0).sum())
    _chk(c, OK if vol0 < 0.01 * len(df) else ATENCAO, "Volume zerado ou ausente", f"{vol0} candles ({vol0 / len(df):.1%})")

    plano = (h == l) & (vol.fillna(0) <= 0)
    _chk(c, OK if plano.sum() < 0.01 * len(df) else ATENCAO, "Candles 'congelados' (máx = mín, sem volume)", f"{int(plano.sum())}")

    ret = np.log(cl).diff()
    lim = 6 * ret.std()
    saltos = ret[ret.abs() > lim]
    primeiro_do_dia = pd.Series(df.index.normalize(), index=df.index).diff().ne(pd.Timedelta(0))
    abertura = primeiro_do_dia.reindex(saltos.index)
    intradia = saltos[~abertura.values]
    _chk(c, OK if len(intradia) == 0 else ATENCAO, f"Saltos de preço anormais (> 6σ = {lim:.2%}) dentro do pregão",
         "nenhum" if intradia.empty else ", ".join(f"{t:%d/%m %H:%M} ({v:+.2%})" for t, v in intradia.head(8).items())
         + " — confira se é notícia, provento ou erro de dado")
    gaps = saltos[abertura.values]
    if len(gaps):
        _chk(c, OK, "Gaps de abertura grandes (> 6σ)", ", ".join(f"{t:%d/%m} ({v:+.2%})" for t, v in gaps.head(8).items()))

    agora = datetime.now(ZoneInfo("America/Sao_Paulo")).replace(tzinfo=None)
    idade = agora - df.index[-1]
    dia_util = agora.weekday() < 5 and 10 <= agora.hour < 18
    nivel = OK if idade < pd.Timedelta("30min") or not dia_util else (ATENCAO if idade < pd.Timedelta("1D") else FALHA)
    _chk(c, nivel, "Atualidade do último candle", f"{df.index[-1]:%d/%m %H:%M}, há {_fmt_td(idade)}"
         + (" (brapi pode ter atraso no intradiário)" if nivel != OK else ""))

    aq = int(df.MA_610.notna().sum()) if "MA_610" in df else 0
    _chk(c, OK if aq >= 500 else (ATENCAO if aq >= 100 else FALHA), "Candles com todos os indicadores calculados",
         f"{aq} de {len(df)} (os primeiros 609 servem de aquecimento da MA610) — aumente o histórico se estiver baixo")
    return pd.DataFrame(c)


def _fmt_td(td):
    m = int(td.total_seconds() // 60)
    return f"{m} min" if m < 120 else (f"{m // 60} h" if m < 2880 else f"{m // 1440} dias")


# ------------------------------------------------------------------ coerência dos indicadores e sinais
def checar_coerencia(df, janela_zona):
    c = []
    d = df[df.MA_610.notna()]
    if d.empty:
        _chk(c, FALHA, "Indicadores", "sem candles com MA610 calculada")
        return pd.DataFrame(c), pd.DataFrame()

    fora = (d.Donchian_Mid > d.Donchian_Upper + 1e-9) | (d.Donchian_Mid < d.Donchian_Lower - 1e-9) | \
           (d.Close > d.Donchian_Upper + 1e-9) | (d.Close < d.Donchian_Lower - 1e-9)
    _chk(c, OK if not fora.any() else FALHA, "Canal contém preço e Mid", f"{int(fora.sum())} violações")

    sinais = d[d.Sinal.isin([SINAL_C, SINAL_V])]
    dup = (sinais.Sinal == sinais.Sinal.shift()).sum()
    _chk(c, OK if dup == 0 else ATENCAO, "Cruzamentos alternam compra/venda",
         f"{len(sinais)} cruzamentos; {int(dup)} repetidos em sequência (perda de cruzamento intermediário)")

    dias = d.index.normalize().nunique()
    _chk(c, OK, "Frequência de cruzamentos", f"{len(sinais) / max(dias, 1):.2f} por pregão")

    pos = np.flatnonzero(d.Sinal.isin([SINAL_C, SINAL_V]).values)
    falsos = int(sum(1 for i, j in zip(pos[:-1], pos[1:]) if j - i <= WHIPSAW_CANDLES))
    pct = falsos / max(len(pos) - 1, 1)
    _chk(c, OK if pct < 0.3 else ATENCAO, f"Whipsaw (cruzamento desfeito em ≤ {WHIPSAW_CANDLES} candles)",
         f"{falsos} de {max(len(pos) - 1, 0)} ({pct:.0%}) — alto = muita indecisão perto da média")

    na_zona = d.Sinal.isin([SINAL_C, SINAL_V]) & d.Zona_Indecisao
    _chk(c, OK, "Cruzamentos dentro da zona de indecisão",
         f"{int(na_zona.sum())} de {len(sinais)} ({na_zona.sum() / max(len(sinais), 1):.0%}) — ruído esperado; prefira o rompimento")

    contra = ((d.Sinal == SINAL_C) & (d.Estado_Canal == "📉 Expansão de Baixa")) | \
             ((d.Sinal == SINAL_V) & (d.Estado_Canal == "📈 Expansão de Alta"))
    _chk(c, OK if contra.sum() <= 0.2 * max(len(sinais), 1) else ATENCAO, "Cruzamento contra a expansão do canal",
         f"{int(contra.sum())} sinais (compra em expansão de baixa / venda em expansão de alta)")

    romp = d[d.Rompimento != ""]
    lado_errado = ((romp.Rompimento == ROMP_A) & (romp.Close < romp.MA_500)) | ((romp.Rompimento == ROMP_B) & (romp.Close > romp.MA_500))
    _chk(c, OK if not lado_errado.any() else ATENCAO, "Rompimento confirmado pelo preço (fecho do lado da MA500)",
         f"{len(romp)} rompimentos; {int(lado_errado.sum())} com fecho do outro lado")

    topo_fundo = ((d.Alerta_Topo != "") & (d.Alerta_Fundo != "")).sum()
    _chk(c, OK if topo_fundo == 0 else FALHA, "Alerta de topo e fundo no mesmo candle", f"{int(topo_fundo)}")

    u = d.iloc[-1]
    alin = _alinhamento(u)
    if u.Close > u.MA_500 and "Expansão de Alta" in u.Estado_Canal:
        tat = "🚀 Continuidade Alta"
    elif u.Close < u.MA_500 and "Expansão de Baixa" in u.Estado_Canal:
        tat = "🩸 Continuidade Baixa"
    else:
        tat = "🔍 Zona de Observação"
    conflito = ("Altista" in alin and "Baixa" in tat) or ("Baixista" in alin and "Alta" in tat)
    _chk(c, OK if not conflito else ATENCAO, "Leitura atual coerente (alinhamento × leitura tática)", f"{alin} × {tat}")

    estado = pd.DataFrame({
        "Item": ["Fecho", "Donchian topo", "Donchian Mid", "Donchian fundo", "MA 500", "MA 610",
                 "Distância Mid×MA500 (fração do canal)", "Largura do canal (%)", "Dinâmica do canal",
                 "Alinhamento estrutural", "Leitura tática", "Zona / rompimento", "Último cruzamento", "Último rompimento"],
        "Valor": [f"{u.Close:.2f}", f"{u.Donchian_Upper:.2f}", f"{u.Donchian_Mid:.2f}", f"{u.Donchian_Lower:.2f}",
                  f"{u.MA_500:.2f}", f"{u.MA_610:.2f}", f"{u.Dist_Rel:+.3f}",
                  f"{(u.Donchian_Upper - u.Donchian_Lower) / u.Close:.2%}", u.Estado_Canal, alin, tat,
                  status_zona(df, janela_zona), _ultimo(d, d.Sinal.isin([SINAL_C, SINAL_V]), "Sinal"),
                  _ultimo(d, d.Rompimento != "", "Rompimento")],
    })
    return pd.DataFrame(c), estado


def _ultimo(d, mask, col):
    if not mask.any():
        return "—"
    t = d.index[mask][-1]
    return f"{d.loc[t, col]} em {t:%d/%m %H:%M} (fecho {d.loc[t, 'Close']:.2f})"


def distribuicoes(df):
    d = df[df.MA_610.notna()]
    est = d.Estado_Canal.value_counts(normalize=True).mul(100).round(1).rename("% do tempo").to_frame()
    est.index.name = "Dinâmica do canal"
    zona = d.Zona_Indecisao.astype(bool)
    blocos = (zona != zona.shift()).cumsum()[zona]
    dur = blocos.value_counts() if len(blocos) else pd.Series(dtype=int)
    resumo = pd.DataFrame({"Métrica": ["Tempo na zona de indecisão", "Períodos na zona", "Duração média na zona (candles)",
                                       "Duração máxima na zona (candles)", "Retorno do período", "Volatilidade por candle (desvio)"],
                           "Valor": [f"{zona.mean():.1%}", f"{len(dur)}", f"{dur.mean():.0f}" if len(dur) else "—",
                                     f"{dur.max():.0f}" if len(dur) else "—",
                                     f"{d.Close.iloc[-1] / d.Close.iloc[0] - 1:+.2%}", f"{np.log(d.Close).diff().std():.3%}"]})
    return est.reset_index(), resumo


# ------------------------------------------------------------------ Kronos
def checar_kronos(ticker, df, sinais_k):
    c = []
    if sinais_k is None or ticker not in sinais_k.index:
        _chk(c, ATENCAO, "Previsão Kronos", "sem previsão para este ativo (o job ainda não rodou ou faltaram dados)")
        return pd.DataFrame(c), pd.DataFrame()
    k = sinais_k.loc[ticker]
    ult_k = pd.to_datetime(k.ultimo_candle)
    atraso = int((df.index > ult_k).sum())
    _chk(c, OK if atraso <= 78 else ATENCAO, "Defasagem da previsão",
         f"gerada em {k.gerado_em} com dados até {ult_k:%d/%m %H:%M}; {atraso} candles novos desde então"
         + (" — a previsão já ficou para trás" if atraso > int(k.pred_len) else ""))
    if ult_k in df.index:
        dif = abs(df.loc[ult_k, "Close"] / k.close - 1)
        _chk(c, OK if dif < 0.002 else ATENCAO, "Mesmo dado na previsão e no app", f"fecho no Kronos {k.close:.2f} × app {df.loc[ult_k, 'Close']:.2f} ({dif:.2%})")
    banda_ok = k.p10_final <= k.med_final <= k.p90_final
    _chk(c, OK if banda_ok else FALHA, "Banda P10 ≤ mediana ≤ P90", f"{k.p10_final:.2f} ≤ {k.med_final:.2f} ≤ {k.p90_final:.2f}")
    u = df.iloc[-1]
    alin = _alinhamento(u)
    discord = ("Altista" in alin and k.prob_alta < 0.3) or ("Baixista" in alin and k.prob_alta > 0.7)
    _chk(c, OK if not discord else ATENCAO, "Kronos × alinhamento Donchian",
         f"{alin} × prob. de alta {k.prob_alta:.0%}" + (" — sinais divergentes, cautela" if discord else ""))
    tab = pd.DataFrame({"Item": ["Amplitude prevista ÷ ATR", "Prob. de alta no horizonte", "Prob. de romper o topo do canal",
                                 "Prob. de romper o fundo do canal", "Mediana no fim do horizonte", "Faixa P10–P90", "Horizonte"],
                        "Valor": [f"{k.razao_amp_atr:.2f}×", f"{k.prob_alta:.0%}", f"{k.prob_rompe_topo:.0%}",
                                  f"{k.prob_rompe_fundo:.0%}", f"{k.med_final:.2f}", f"{k.p10_final:.2f} – {k.p90_final:.2f}",
                                  f"{int(k.pred_len)} candles"]})
    return pd.DataFrame(c), tab


# ------------------------------------------------------------------ HTML
CSS = """
:root{--bg:#fff;--fg:#1d2329;--mut:#5f6b76;--card:#f5f7f9;--bd:#dde3e8;--ac:#2962ff}
@media (prefers-color-scheme:dark){:root{--bg:#14181c;--fg:#e6eaee;--mut:#9aa6b1;--card:#1d2328;--bd:#2c343b;--ac:#6f8dff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:1100px;margin:auto;padding:16px}h1{font-size:1.5rem;margin:.2em 0}h2{font-size:1.15rem;margin:1.6em 0 .5em;padding-bottom:.25em;border-bottom:2px solid var(--ac)}
.mut{color:var(--mut);font-size:.9rem}.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0}
.kpi{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:10px 12px}.kpi b{display:block;font-size:1.35rem}
.tw{overflow-x:auto;border:1px solid var(--bd);border-radius:8px;margin:6px 0 10px}table{border-collapse:collapse;width:100%;font-size:.86rem}
th,td{padding:6px 9px;border-bottom:1px solid var(--bd);text-align:left;white-space:nowrap}th{background:var(--card);position:sticky;top:0}
td:last-child{white-space:normal}tr:last-child td{border-bottom:0}.nota{background:var(--card);border-left:4px solid var(--ac);padding:8px 12px;border-radius:6px;font-size:.9rem}
"""


def _tab(df):
    if df is None or df.empty:
        return "<p class='mut'>Sem dados.</p>"
    return f"<div class='tw'>{df.to_html(index=False, escape=True, border=0, na_rep='—')}</div>"


def gerar_relatorio_html(ticker, periodo, df, params, ev_resumo, sinais_k=None, fig=None):
    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    dados = checar_dados(df)
    coer, estado = checar_coerencia(df, params["janela_zona"])
    estados, resumo = distribuicoes(df)
    kchk, ktab = checar_kronos(ticker, df, sinais_k)
    todos = pd.concat([dados, coer, kchk], ignore_index=True)
    cont = todos[""].value_counts()

    novo = lambda m: m & ~m.shift(1, fill_value=False)   # toques: só o 1º candle de cada sequência
    eventos = df[(df.Sinal != "Aguardar") | (df.Rompimento != "") | novo(df.Alerta_Topo != "") | novo(df.Alerta_Fundo != "")]
    eventos = eventos[["Close", "MA_500", "Donchian_Mid", "Dist_Rel", "Estado_Canal", "Sinal", "Rompimento", "Alerta_Topo", "Alerta_Fundo"]]
    eventos = eventos.sort_index(ascending=False).head(100).round(3).reset_index()
    eventos["Date"] = eventos["Date"].dt.strftime("%d/%m/%Y %H:%M")

    val = ev_resumo.drop(columns=["h"], errors="ignore") if ev_resumo is not None else pd.DataFrame()
    if not val.empty:
        val.insert(0, "", np.where(val.N < 20, ATENCAO, OK))

    grafico = ""
    if fig is not None:
        try:
            grafico = "<h2>Gráfico</h2>" + fig.to_html(full_html=False, include_plotlyjs="cdn", config={"responsive": True})
        except Exception:
            grafico = ""

    p = params
    corpo = f"""
<h1>Relatório de coerência — {html.escape(ticker)}</h1>
<p class='mut'>Gerado em {agora:%d/%m/%Y %H:%M} · histórico {html.escape(periodo)} em 5 min · Donchian 305 · MA 500/610 ·
zona &lt; {p['limiar_zona']:.2f} · rompimento &gt; {p['limiar_romp']:.2f} · janela {p['janela_zona']} candles</p>
<div class='kpis'>
<div class='kpi'><span class='mut'>Verificações OK</span><b>{cont.get(OK, 0)} {OK}</b></div>
<div class='kpi'><span class='mut'>Atenção</span><b>{cont.get(ATENCAO, 0)} {ATENCAO}</b></div>
<div class='kpi'><span class='mut'>Falhas</span><b>{cont.get(FALHA, 0)} {FALHA}</b></div>
<div class='kpi'><span class='mut'>Candles</span><b>{len(df)}</b></div>
<div class='kpi'><span class='mut'>Fecho</span><b>{df.Close.iloc[-1]:.2f}</b></div>
</div>
<h2>1. Situação atual</h2>{_tab(estado)}
<h2>2. Qualidade dos dados</h2>{_tab(dados)}
<h2>3. Coerência dos indicadores e sinais</h2>{_tab(coer)}
<h2>4. Distribuição do tempo</h2>{_tab(estados)}{_tab(resumo)}
<h2>5. Validação dos sinais × entrada aleatória</h2>
<p class='nota'>Retorno e movimento máximo medidos no sentido do sinal, a partir do fecho do candle do evento. <b>Vantagem</b> &gt; 0 = o evento supera
uma entrada aleatória no mesmo sentido. {ATENCAO} = menos de 20 ocorrências (pouco confiável). Horizontes: {', '.join(f'{h} candles ({n})' for h, n in HORIZONTES.items())}.</p>
{_tab(val)}
<h2>6. Kronos</h2>{_tab(kchk)}{_tab(ktab)}
{grafico}
<h2>7. Registo de eventos (últimos {len(eventos)})</h2>{_tab(eventos)}
<p class='mut'>Relatório para análise; não é recomendação de investimento.</p>"""
    return f"""<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Relatório {html.escape(ticker)} {agora:%d-%m-%Y}</title><style>{CSS}</style></head><body><main>{corpo}</main></body></html>"""


def exportar_csv(df):
    cols = [c for c in ["Open", "High", "Low", "Close", "Volume", "MA_500", "MA_610", "Donchian_Upper", "Donchian_Mid",
                        "Donchian_Lower", "Dist_Rel", "Zona_Indecisao", "Estado_Canal", "Sinal", "Rompimento",
                        "Alerta_Topo", "Alerta_Fundo"] if c in df]
    return df[cols].round(4).to_csv(sep=";", decimal=",").encode("utf-8-sig")   # abre direto no Excel em português
