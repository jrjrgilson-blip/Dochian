import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
import importlib

# Após um git pull o Streamlit Cloud recarrega este arquivo, mas pode manter os módulos antigos em memória
# (ImportError de função nova). Recarregar a cada execução é barato e evita isso.
import donchian_core, donchian_graficos, donchian_backtest, donchian_relatorio
for _m in (donchian_core, donchian_graficos, donchian_backtest, donchian_relatorio):
    importlib.reload(_m)

from donchian_core import (WATCHLIST_B3, SINAL_C, SINAL_V, HORIZONTES, INTERVALOS, rotulo_h, carregar_brapi,
                           carregar_historico, juntar, reamostrar,
                           processar_indicadores, status_zona, resultados_eventos, resumir_validacao)
from donchian_graficos import grafico_ativo, grafico_validacao, grafico_curvas
from donchian_backtest import ESTRATEGIAS, backtest, resumo, curva_capital
from donchian_relatorio import gerar_relatorio_html, exportar_csv

st.set_page_config(page_title="Laboratório Donchian - Scanner de Mercado", layout="wide")

st.title("🔬 Scanner Institucional: Donchian (305) & Ciclos")

# Acesso ao cofre do Streamlit
try:
    BRAPI_TOKEN = st.secrets["BRAPI_TOKEN"]
except Exception:
    st.error("Chave não encontrada no secrets.")
    st.stop()

# --- PAINEL LATERAL DE CONTROLO ---
st.sidebar.header("⚙️ Painel de Controlo")
modo_visao = st.sidebar.radio("Modo de Operação:", options=["📊 Scanner Geral (Ranking)", "📈 Análise Individual por Ativo"])

ativo_escolhido = st.sidebar.selectbox("Selecione o Ativo para Análise Detalhada:", options=WATCHLIST_B3, index=0)

intervalo = st.sidebar.radio("Tempo gráfico:", options=list(INTERVALOS), horizontal=True,
                             format_func=lambda i: f"{INTERVALOS[i]} min",
                             help="A brapi limita o intradiário de 5 e 15 min a ~60 dias; 60 min costuma ter bem mais histórico. "
                                  "Os períodos dos indicadores (305, 500, 610) e os horizontes continuam em número de candles.")
MINUTOS = INTERVALOS[intervalo]

opcao_periodo = st.sidebar.selectbox(
    f"Quantidade de Histórico ({MINUTOS} min):",
    options=["1 Mês", "3 Meses", "6 Meses", "1 Ano", "2 Anos"],
    index={"5m": 1, "15m": 2}.get(intervalo, 4),
    help="A brapi limita o histórico intradiário; o app mostra o período que realmente veio."
)

mapa_periodos = {
    "1 Mês": "1mo",
    "3 Meses": "3mo",
    "6 Meses": "6mo",
    "1 Ano": "1y",
    "2 Anos": "2y"
}
range_api = mapa_periodos[opcao_periodo]
usar_hist = st.sidebar.checkbox("Usar histórico acumulado no repositório", value=True,
                                help="Candles de 5 min guardados todo dia pelo GitHub Actions + os mais recentes da brapi. "
                                     "15 e 60 min são montados a partir dos 5 min. Desligado = só o que a brapi entrega (~60 dias).")

st.sidebar.divider()
st.sidebar.subheader("⚖️ Zona de indecisão & rompimento")
limiar_zona = st.sidebar.slider("Zona: Mid a menos de X da MA500 (fração da largura do canal)", 0.02, 0.30, 0.08, 0.01)
limiar_romp = st.sidebar.slider("Rompimento: distância passa de", 0.05, 0.60, 0.20, 0.01)
janela_zona = st.sidebar.slider("Só conta rompimento se esteve na zona nos últimos N candles", 12, 300, 60, 6)
if limiar_romp <= limiar_zona:
    st.sidebar.warning("O limiar de rompimento deve ser maior que o da zona.")
n_grafico = st.sidebar.slider("Candles no gráfico", 300, 6000, 1500, 100)
horizonte_sel = st.sidebar.selectbox("Horizonte da validação", options=list(HORIZONTES), index=1,
                                     format_func=lambda h: f"{h} candles ({rotulo_h(h, MINUTOS)})")
janela_incl = st.sidebar.slider("Dinâmica do canal: inclinação medida em N candles", 5, 150, 10, 5,
                                help="10 = comportamento original. Com 305 candles de canal, 50–100 dá uma leitura menos 'Lateral'.")

st.sidebar.divider()
st.sidebar.subheader("📈 Backtest por operação")
stop_atr = st.sidebar.slider("Stop (× ATR de 14 candles na entrada; 0 = sem stop)", 0.0, 10.0, 0.0, 0.5)
custo_lado = st.sidebar.number_input("Custo por lado (%)", 0.0, 0.5, 0.03, 0.01, format="%.2f")
sentido = st.sidebar.radio("Sentido", ["ambos", "compra"], horizontal=True,
                           format_func=lambda s: "Compra e venda" if s == "ambos" else "Só compra")
estrategia_foco = st.sidebar.selectbox("Estratégia em destaque (scanner, operações e relatório)", list(ESTRATEGIAS),
                                       index=list(ESTRATEGIAS).index("canal"), format_func=lambda e: ESTRATEGIAS[e])
PARAMS = dict(limiar_zona=limiar_zona, limiar_romp=limiar_romp, janela_zona=janela_zona, janela_incl=janela_incl)
BT = dict(limiar_zona=limiar_zona, stop_atr=stop_atr, custo_lado=custo_lado, sentido=sentido)
BT_CFG = (f"Stop {stop_atr:g}× ATR" if stop_atr else "Sem stop") + f" · custo {custo_lado:.2f}% por lado · " + \
         ("compra e venda" if sentido == "ambos" else "só compra")


def tabela_backtest(ops_por_estrategia):
    t = pd.DataFrame([resumo(o, ESTRATEGIAS[e]) for e, o in ops_por_estrategia.items()])
    fmt = lambda v: "—" if pd.isna(v) else (f"{v:.0f}" if float(v).is_integer() else f"{v:.2f}")
    return t.set_index("Estratégia").T.map(fmt).reset_index().rename(columns={"index": "Métrica"})


CAPTION_BT = ("**Rompimento:** entra na abertura seguinte ao ★ e sai quando o Mid volta à zona (ou no rompimento contrário). "
              "**Todo cruzamento:** compra/vende em cada cruzamento Mid×MA500 e vira no contrário — mostra o custo de "
              "operar a indecisão. **Canal:** entra quando o Mid passa acima (compra) ou abaixo (venda) das MA500 e MA610; o stop "
              "acompanha o canal inferior na compra e o superior na venda, e a operação só termina quando o preço toca esse canal. "
              "Depois espera um novo rompimento. **Canal com alvo:** igual, mas também encerra ao tocar o canal a favor. Payoff = ganho médio ÷ perda média; fator de lucro = soma dos ganhos ÷ soma das perdas (> 1 = lucrativo). "
              "Poucas operações = pouca confiança.")


@st.cache_data(ttl=300)
def carregar_dados_ativo(ticker, range_val, token, interval="5m"):
    return carregar_brapi(ticker, range_val, token, interval)


@st.cache_data(ttl=600)
def carregar_hist_local(ticker):
    return carregar_historico(ticker)


MESES = {"1mo": 1, "3mo": 3, "6mo": 6, "1y": 12, "2y": 24}


def obter_dados(ticker):
    if not usar_hist:
        return carregar_dados_ativo(ticker, range_api, BRAPI_TOKEN, intervalo)
    df = juntar(carregar_hist_local(ticker), carregar_dados_ativo(ticker, "1mo", BRAPI_TOKEN, "5m"))
    if df.empty:
        return df
    df = df[df.index >= df.index[-1] - pd.DateOffset(months=MESES[range_api])]
    return reamostrar(df, MINUTOS)


@st.cache_data(ttl=600)
def carregar_kronos():
    """Previsões geradas pelo GitHub Actions (kronos_job.py). Ausentes = recurso desligado."""
    base = Path(__file__).parent / "data"
    try:
        sinais = pd.read_csv(base / "kronos_sinais.csv")
        prev = pd.read_csv(base / "kronos_previsao.csv", parse_dates=["timestamps"])
        return sinais.set_index("ticker"), prev
    except Exception:
        return None, None


sinais_k, prev_k = carregar_kronos()
if intervalo != "5m":   # o Kronos prevê candles de 5 min; não mistura com outro tempo gráfico
    sinais_k = prev_k = None


def colunas_kronos(ticker, zona_txt):
    if sinais_k is None or ticker not in sinais_k.index:
        return {}
    k = sinais_k.loc[ticker]
    alerta = "🔥 Zona + expansão prevista" if zona_txt.startswith("⚖️") and k.razao_amp_atr >= 1.2 else ""
    return {
        "Kronos: amplitude ÷ ATR": f"{k.razao_amp_atr:.2f}×",
        "Kronos: prob. alta": f"{k.prob_alta:.0%}",
        "Alerta Kronos": alerta,
    }


def mostrar_validacao(ev, base, titulo):
    res = resumir_validacao(ev, base, MINUTOS)
    if res.empty:
        st.info("Nenhum evento com horizonte completo para validar neste período.")
        return
    st.plotly_chart(grafico_validacao(res, horizonte_sel), use_container_width=True)
    filtro = res[res.h == horizonte_sel].drop(columns=["h", "Horizonte"])
    st.dataframe(filtro, use_container_width=True, hide_index=True)
    with st.expander("Todos os horizontes"):
        st.dataframe(res.drop(columns=["h"]), use_container_width=True, hide_index=True)
    st.caption(
        f"**{titulo}.** *Retorno* e *movimento máximo a favor* são medidos no sentido do sinal, "
        "a partir do fecho do candle do evento. *Aleatório* = entrar no mesmo sentido em qualquer candle. "
        "*Vantagem* > 0 de forma consistente indica que o evento acrescenta informação. "
        "Nos toques, acerto < 50% indica **exaustão** (reversão); > 50%, continuação. "
        "Desconfie de N pequeno (< 20)."
    )


# --- MODO 1: SCANNER GERAL (RANKING) ---
if modo_visao == "📊 Scanner Geral (Ranking)":
    st.markdown("### 🔍 Radar de Oportunidades (Ativos de Alta Liquidez)")
    st.write("A varrer o mercado em busca do estado atual de cada ativo com base no Donchian (305) e Médias (500/610)...")

    resultados_scanner, evs, bases, bt_linhas, bt_ops = [], [], [], [], []

    with st.spinner("A processar indicadores de toda a watchlist..."):
        for ticker in WATCHLIST_B3:
            df_temp = obter_dados(ticker)
            if not df_temp.empty and len(df_temp) >= 610:
                df_proc = processar_indicadores(df_temp, **PARAMS)
                if df_proc is not None:
                    ult = df_proc.iloc[-1]

                    mid = ult['Donchian_Mid']
                    ma500 = ult['MA_500']
                    ma610 = ult['MA_610']

                    if mid > ma500 and ma500 > ma610:
                        alinhamento = "🟢 Altista Perfeito"
                    elif mid < ma500 and ma500 < ma610:
                        alinhamento = "🔴 Baixista Perfeito"
                    else:
                        alinhamento = "⚖️ Emaranhado / Transição"

                    zona_txt = status_zona(df_proc, janela_zona)
                    resultados_scanner.append({
                        "Ativo": ticker,
                        "Fecho (R$)": round(ult['Close'], 2),
                        "Dinâmica do Canal": ult['Estado_Canal'],
                        "Alinhamento Estrutural": alinhamento,
                        "Zona / Rompimento": zona_txt,
                        "Dist. Mid×MA500": round(ult['Dist_Rel'], 3),
                        "Alerta Atual": ult['Alerta_Fundo'] if ult['Alerta_Fundo'] != "" else (ult['Alerta_Topo'] if ult['Alerta_Topo'] != "" else "Nenhum"),
                        **colunas_kronos(ticker, zona_txt),
                        "Atualização": df_proc.index[-1].strftime('%d/%m %H:%M')
                    })
                    ev, base = resultados_eventos(df_proc, ticker=ticker)
                    evs.append(ev)
                    o_r = backtest(df_proc, estrategia_foco, **BT)
                    bt_linhas.append({"Ativo": ticker, **resumo(o_r)})
                    bt_ops.append(o_r)
                    bases.append(base)

    if resultados_scanner:
        df_ranking = pd.DataFrame(resultados_scanner)
        df_ranking = df_ranking.sort_values(by="Ativo", ascending=True)
        st.dataframe(df_ranking, use_container_width=True, height=500, hide_index=True)
        if intervalo != "5m":
            st.caption("🤖 Colunas do Kronos ocultas: as previsões são de candles de 5 min.")
        if sinais_k is not None:
            st.caption(f"🤖 Kronos gerado em {sinais_k.gerado_em.iloc[0]} — previsão dos próximos "
                       f"{int(sinais_k.pred_len.iloc[0])} candles. *Amplitude ÷ ATR* > 1 = mais volatilidade que o normal.")
        st.success("✅ Varrimento concluído com sucesso!")

        st.divider()
        st.subheader(f"📈 Backtest por operação, por ativo — {ESTRATEGIAS[estrategia_foco]}")
        tb = pd.DataFrame(bt_linhas).drop(columns=["Estratégia"]).set_index("Ativo")
        todas = [o for o in bt_ops if not o.empty]
        if todas:
            tot = resumo(pd.concat(todas, ignore_index=True).sort_values("Saída"))
            tot.update({"Resultado composto (%)": round(tb["Resultado composto (%)"].mean(), 2), "Drawdown máx. (%)": np.nan})
            tot.pop("Estratégia")
            tb.loc["TOTAL (composto = média por ativo)"] = pd.Series(tot)
        st.dataframe(tb, use_container_width=True)
        st.caption(f"{BT_CFG}. " + CAPTION_BT)

        st.divider()
        st.subheader("🧪 Validação dos sinais — watchlist inteira")
        mostrar_validacao(pd.concat(evs, ignore_index=True), pd.concat(bases, ignore_index=True),
                          f"{len(evs)} ativos, {opcao_periodo}")
    else:
        st.error("Não foi possível carregar os dados para o ranking neste momento.")

# --- MODO 2: ANÁLISE INDIVIDUAL & REGISTO COMPLETO ---
else:
    st.markdown(f"### 📈 Análise Detalhada & Eventos: **{ativo_escolhido}**")

    df = obter_dados(ativo_escolhido)

    if not df.empty:
        st.info(f"📊 Foram processados **{len(df)}** candles de {MINUTOS} minutos{' do histórico acumulado + brapi' if usar_hist else ' da brapi'} (Período: {df.index[0].strftime('%d/%m/%Y')} até {df.index[-1].strftime('%d/%m/%Y %H:%M')}).")

        if len(df) < 610:
            st.warning(f"⚠️ Atenção: O histórico tem apenas {len(df)} velas. A média de 610 precisa de mais dados.")

        df = processar_indicadores(df, **PARAMS)

        if df is not None:
            ult_close = df['Close'].iloc[-1]
            ult_ma500 = df['MA_500'].iloc[-1]
            ult_ma610 = df['MA_610'].iloc[-1]
            ult_mid = df['Donchian_Mid'].iloc[-1]
            ult_estado = df['Estado_Canal'].iloc[-1]

            medias_alinhadas_alta = (ult_mid > ult_ma500) and (ult_ma500 > ult_ma610)
            medias_alinhadas_baixa = (ult_mid < ult_ma500) and (ult_ma500 < ult_ma610)

            # Cartões de Diagnóstico
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric(label="Dinâmica do Canal", value=ult_estado)
            with col2:
                if medias_alinhadas_alta:
                    st.metric(label="Alinhamento Estrutural", value="🟢 Altista Perfeito")
                elif medias_alinhadas_baixa:
                    st.metric(label="Alinhamento Estrutural", value="🔴 Baixista Perfeito")
                else:
                    st.metric(label="Alinhamento Estrutural", value="⚖️ Transição")
            with col3:
                if ult_close > ult_ma500 and "Expansão de Alta" in ult_estado:
                    st.metric(label="Leitura Tática", value="🚀 Continuidade Alta")
                elif ult_close < ult_ma500 and "Expansão de Baixa" in ult_estado:
                    st.metric(label="Leitura Tática", value="🩸 Continuidade Baixa")
                else:
                    st.metric(label="Leitura Tática", value="🔍 Zona de Observação")
            with col4:
                st.metric(label="Zona / Rompimento", value=status_zona(df, janela_zona))

            area_relatorio = st.container()  # preenchido no fim, quando o gráfico e a validação já existem

            kz = colunas_kronos(ativo_escolhido, status_zona(df, janela_zona))
            if kz:
                k = sinais_k.loc[ativo_escolhido]
                st.info(f"🤖 **Kronos** (próximos {int(k.pred_len)} candles, gerado em {k.gerado_em}): "
                        f"amplitude prevista **{kz['Kronos: amplitude ÷ ATR']}** o ATR · prob. de alta **{kz['Kronos: prob. alta']}** · "
                        f"prob. de romper topo/fundo do canal **{k.prob_rompe_topo:.0%} / {k.prob_rompe_fundo:.0%}** "
                        f"{kz['Alerta Kronos']}")

            st.divider()

            # Gráfico interativo + botão de Tela Cheia TradingView
            col_cab, col_btn = st.columns([3, 1])
            with col_cab:
                st.subheader(f"📈 Gráfico Donchian & Zona de Indecisão: {ativo_escolhido}")
            with col_btn:
                url_tv = f"https://br.tradingview.com/chart/?symbol=BMFBOVESPA%3A{ativo_escolhido}"
                st.markdown(f"""
                    <a href="{url_tv}" target="_blank" style="display:inline-block;background-color:#2962FF;color:white;padding:10px 16px;border-radius:6px;text-decoration:none;font-weight:bold;text-align:center;margin-top:5px;">
                        🖨️ TradingView ↗
                    </a>
                """, unsafe_allow_html=True)

            prev_ativo = prev_k[prev_k.ticker == ativo_escolhido] if prev_k is not None else None
            fig_ativo = grafico_ativo(df, n_grafico, limiar_zona, limiar_romp, prev_ativo, ativo_escolhido)
            st.plotly_chart(fig_ativo,
                            use_container_width=True, config={"scrollZoom": True})
            st.caption("🟨 Faixas amarelas = zona de indecisão (Mid colado na MA500). ★ = rompimento após a zona. "
                       "No painel de baixo, tracejado = limiar da zona, pontilhado = limiar do rompimento.")

            st.divider()
            st.subheader(f"🧪 Validação dos sinais: {ativo_escolhido}")
            ev, base = resultados_eventos(df, ticker=ativo_escolhido)
            mostrar_validacao(ev, base, f"{ativo_escolhido}, {opcao_periodo}")

            st.divider()
            st.subheader(f"📈 Backtest por operação: {ativo_escolhido}")
            ops_todas = {e: backtest(df, e, **BT) for e in ESTRATEGIAS}
            ops_r = ops_todas[estrategia_foco]
            tab_bt = tabela_backtest(ops_todas)
            col_t, col_g = st.columns([1, 1.4])
            with col_t:
                st.dataframe(tab_bt, use_container_width=True, hide_index=True, height=520)
            with col_g:
                st.plotly_chart(grafico_curvas({ESTRATEGIAS[e]: curva_capital(o) for e, o in ops_todas.items()}),
                                use_container_width=True)
            st.caption(f"{BT_CFG}. " + CAPTION_BT)
            if not ops_r.empty:
                with st.expander(f"Operações — {ESTRATEGIAS[estrategia_foco]} ({len(ops_r)})"):
                    st.dataframe(ops_r.sort_values("Entrada", ascending=False).round(dict.fromkeys(ops_r.select_dtypes("number").columns, 2)),
                                 use_container_width=True, hide_index=True)

            # --- RELATÓRIO SOB DEMANDA (só é gerado ao tocar no botão) ---
            with area_relatorio:
                chave_rel = (ativo_escolhido, range_api, intervalo, usar_hist, tuple(PARAMS.values()), tuple(BT.values()), str(df.index[-1]))
                rel = st.session_state.get("relatorio")
                c_rel1, c_rel2, c_rel3 = st.columns([1.2, 1, 1])
                with c_rel1:
                    if st.button("📄 Gerar relatório de coerência", use_container_width=True):
                        with st.spinner("A montar o relatório..."):
                            html_rel = gerar_relatorio_html(ativo_escolhido, opcao_periodo, df, PARAMS,
                                                            resumir_validacao(ev, base, MINUTOS), sinais_k, fig_ativo,
                                                            tab_bt, ops_r, BT_CFG, intervalo)
                            rel = {"chave": chave_rel, "html": html_rel.encode("utf-8"), "csv": exportar_csv(df)}
                            st.session_state["relatorio"] = rel
                if rel and rel["chave"] == chave_rel:
                    nome = f"relatorio_{ativo_escolhido}_{intervalo}_{df.index[-1]:%Y%m%d_%H%M}"
                    with c_rel2:
                        st.download_button("⬇️ Relatório (HTML)", rel["html"], f"{nome}.html", "text/html", use_container_width=True)
                    with c_rel3:
                        st.download_button("⬇️ Dados + indicadores (CSV)", rel["csv"], f"{nome}.csv", "text/csv", use_container_width=True)
                elif rel:
                    st.caption("Os parâmetros ou os dados mudaram desde o último relatório — gere de novo.")

            # --- TABELA DE EVENTOS COMPLETA (Cruzamentos com Amplitude + Toques de Topo/Fundo + Rompimentos) ---
            st.subheader("📋 Registo Histórico de Sinais, Topos, Fundos & Amplitude")

            df_eventos = df[(df['Sinal'].isin([SINAL_C, SINAL_V])) | (df['Alerta_Fundo'] != "") | (df['Alerta_Topo'] != "") | (df['Rompimento'] != "")].copy()

            if not df_eventos.empty:
                df_eventos = df_eventos.sort_index(ascending=True)

                # Amplitude acumulada entre cruzamentos de sinal
                df_cruz_temp = df_eventos[df_eventos['Sinal'].isin([SINAL_C, SINAL_V])].copy()
                df_cruz_temp['Preco_Anterior_Sinal'] = df_cruz_temp['Close'].shift(1)
                df_cruz_temp['Amplitude Ciclo (%)'] = (((df_cruz_temp['Close'] - df_cruz_temp['Preco_Anterior_Sinal']) / df_cruz_temp['Preco_Anterior_Sinal']) * 100).round(2)
                df_cruz_temp['Amplitude Ciclo (%)'] = df_cruz_temp['Amplitude Ciclo (%)'].apply(
                    lambda x: f"+{x}%" if pd.notnull(x) and x > 0 else (f"{x}%" if pd.notnull(x) else "-")
                )

                df_eventos['Amplitude Ciclo (%)'] = "-"
                df_eventos.update(df_cruz_temp[['Amplitude Ciclo (%)']])

                ordem_exibicao = st.radio("Ordenar histórico de eventos:", options=["Mais recentes primeiro", "Mais antigos primeiro"], horizontal=True)
                df_eventos = df_eventos.sort_index(ascending=(ordem_exibicao == "Mais antigos primeiro"))

                df_mostrar = df_eventos[['Close', 'Amplitude Ciclo (%)', 'MA_500', 'Donchian_Mid', 'Estado_Canal', 'Sinal', 'Rompimento', 'Alerta_Fundo', 'Alerta_Topo']].round(2)
                st.dataframe(df_mostrar, use_container_width=True, height=450)

                st.caption("ℹ️ *A coluna 'Amplitude Ciclo (%)' calcula a variação acumulada entre cruzamentos de sinal, enquanto os alertas indicam os toques nas extremidades do Canal de Donchian.*")
            else:
                st.warning("Nenhum evento relevante registado no período selecionado para este ativo.")
    else:
        st.error("Nenhum dado retornado para o ativo selecionado.")
