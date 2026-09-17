import streamlit as st
import requests
import pandas as pd
import numpy as np

st.set_page_config(page_title="Laboratório Donchian - Scanner de Mercado", layout="wide")

st.title("🔬 Scanner Institucional: Donchian (305) & Ciclos")

# Acesso ao cofre do Streamlit
try:
    BRAPI_TOKEN = st.secrets["BRAPI_TOKEN"]
except:
    st.error("Chave não encontrada no secrets.")
    st.stop()

# --- WATCHLIST DE ALTA LIQUIDEZ ---
WATCHLIST_B3 = [
    "BOVA11", "PETR4", "VALE3", "ITUB4", "BBAS3", 
    "BBDC4", "SANB11", "USIM5", "CSNA3", "WEGE3", 
    "ABEV3", "RENT3", "SUZB3"
]

# --- PAINEL LATERAL DE CONTROLO ---
st.sidebar.header("⚙️ Painel de Controlo")
modo_visao = st.sidebar.radio("Modo de Operação:", options=["📊 Scanner Geral (Ranking)", "📈 Análise Individual por Ativo"])

ativo_escolhido = st.sidebar.selectbox("Selecione o Ativo para Análise Detalhada:", options=WATCHLIST_B3, index=0)

opcao_periodo = st.sidebar.selectbox(
    "Quantidade de Histórico (5m):", 
    options=["1 Mês", "3 Meses", "6 Meses (Máximo API)"], 
    index=1
)

mapa_periodos = {
    "1 Mês": "1mo",
    "3 Meses": "3mo",
    "6 Meses (Máximo API)": "6mo"
}
range_api = mapa_periodos[opcao_periodo]

@st.cache_data(ttl=300)
def carregar_dados_ativo(ticker, range_val, token):
    url = f"https://brapi.dev/api/quote/{ticker}?range={range_val}&interval=5m"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        resp = requests.get(url, headers=headers).json()
        if 'results' in resp and resp['results']:
            hist = resp['results'][0].get('historicalDataPrice', [])
            df = pd.DataFrame(hist)
            if not df.empty:
                df['Date'] = pd.to_datetime(df['date'], unit='s', utc=True)
                df['Date'] = df['Date'].dt.tz_convert('America/Sao_Paulo').dt.tz_localize(None)
                df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
                df.set_index('Date', inplace=True)
                return df
    except Exception as e:
        pass
    return pd.DataFrame()

# Função para processar os indicadores num DataFrame
def processar_indicadores(df):
    if len(df) < 610:
        return None
        
    df['MA_500'] = df['Close'].rolling(window=500).mean()
    df['MA_610'] = df['Close'].rolling(window=610).mean()
    
    df['Donchian_Upper'] = df['High'].rolling(window=305).max()
    df['Donchian_Lower'] = df['Low'].rolling(window=305).min()
    df['Donchian_Mid'] = (df['Donchian_Upper'] + df['Donchian_Lower']) / 2
    
    df['Upper_Slope'] = df['Donchian_Upper'].diff(10)
    df['Lower_Slope'] = df['Donchian_Lower'].diff(10)
    
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
    df.loc[compra_mask, 'Sinal'] = "🟢 CRUZAMENTO COMPRA"
    
    venda_mask = (df['Donchian_Mid'] < df['MA_500']) & (donch_mid_prev >= ma_500_prev)
    df.loc[venda_mask, 'Sinal'] = "🔴 CRUZAMENTO VENDA"
    
    alerta_fundo_mask = (df['Low'] <= df['Donchian_Lower']) & (df['Close'] < df['MA_500'])
    df.loc[alerta_fundo_mask, 'Alerta_Fundo'] = "⚠️ Tocou Fundo / Exaustão"

    alerta_topo_mask = (df['High'] >= df['Donchian_Upper']) & (df['Close'] > df['MA_500'])
    df.loc[alerta_topo_mask, 'Alerta_Topo'] = "🎯 Tocou Topo / Alvo"
    
    return df

# --- MODO 1: SCANNER GERAL (RANKING) ---
if modo_visao == "📊 Scanner Geral (Ranking)":
    st.markdown("### 🔍 Radar de Oportunidades (Ativos de Alta Liquidez)")
    st.write("A varrer o mercado em busca do estado atual de cada ativo com base no Donchian (305) e Médias (500/610)...")
    
    resultados_scanner = []
    
    with st.spinner("A processar indicadores de toda a watchlist..."):
        for ticker in WATCHLIST_B3:
            df_temp = carregar_dados_ativo(ticker, range_val=range_api, token=BRAPI_TOKEN)
            if not df_temp.empty and len(df_temp) >= 610:
                df_proc = processar_indicadores(df_temp)
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
                        
                    resultados_scanner.append({
                        "Ativo": ticker,
                        "Fecho (R$)": round(ult['Close'], 2),
                        "Dinâmica do Canal": ult['Estado_Canal'],
                        "Alinhamento Estrutural": alinhamento,
                        "Alerta Atual": ult['Alerta_Fundo'] if ult['Alerta_Fundo'] != "" else (ult['Alerta_Topo'] if ult['Alerta_Topo'] != "" else "Nenhum"),
                        "Atualização": df_proc.index[-1].strftime('%d/%m %H:%M')
                    })
                    
    if resultados_scanner:
        df_ranking = pd.DataFrame(resultados_scanner)
        df_ranking = df_ranking.sort_values(by="Ativo", ascending=True)
        st.dataframe(df_ranking, use_container_width=True, height=500)
        st.success("✅ Varrimento concluído com sucesso!")
    else:
        st.error("Não foi possível carregar os dados para o ranking neste momento.")

# --- MODO 2: ANÁLISE INDIVIDUAL & REGISTO COMPLETO ---
else:
    st.markdown(f"### 📈 Análise Detalhada & Eventos: **{ativo_escolhido}**")
    
    df = carregar_dados_ativo(ativo_escolhido, range_api, BRAPI_TOKEN)
    
    if not df.empty:
        st.info(f"📊 Foram processados **{len(df)}** candles de 5 minutos (Período: {df.index[0].strftime('%d/%m/%Y')} até {df.index[-1].strftime('%d/%m/%Y %H:%M')}).")
        
        if len(df) < 610:
            st.warning(f"⚠️ Atenção: O histórico tem apenas {len(df)} velas. A média de 610 precisa de mais dados.")
        
        df = processar_indicadores(df)
        
        if df is not None:
            ult_close = df['Close'].iloc[-1]
            ult_ma500 = df['MA_500'].iloc[-1]
            ult_ma610 = df['MA_610'].iloc[-1]
            ult_mid = df['Donchian_Mid'].iloc[-1]
            ult_estado = df['Estado_Canal'].iloc[-1]
            
            medias_alinhadas_alta = (ult_mid > ult_ma500) and (ult_ma500 > ult_ma610)
            medias_alinhadas_baixa = (ult_mid < ult_ma500) and (ult_ma500 < ult_ma610)

            # Cartões de Diagnóstico
            col1, col2, col3 = st.columns(3)
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

            st.divider()

            # Botão de Tela Cheia TradingView
            col_cab, col_btn = st.columns([3, 1])
            with col_cab:
                st.subheader(f"📈 Gráfico Oficial TradingView: {ativo_escolhido}")
            with col_btn:
                url_tv = f"https://br.tradingview.com/chart/?symbol=BMFBOVESPA%3A{ativo_escolhido}"
                st.markdown(f"""
                    <a href="{url_tv}" target="_blank" style="display:inline-block;background-color:#2962FF;color:white;padding:10px 16px;border-radius:6px;text-decoration:none;font-weight:bold;text-align:center;margin-top:5px;">
                        🖨️ Abrir Tela Cheia ↗
                    </a>
                """, unsafe_allow_html=True)

            # --- TABELA DE EVENTOS COMPLETA (Cruzamentos com Amplitude + Toques de Topo/Fundo) ---
            st.subheader("📋 Registo Histórico de Sinais, Topos, Fundos & Amplitude")
            
            # Filtramos todas as linhas que contenham cruzamento OU toques nas extremidades
            df_eventos = df[(df['Sinal'].isin(["🟢 CRUZAMENTO COMPRA", "🔴 CRUZAMENTO VENDA"])) | (df['Alerta_Fundo'] != "") | (df['Alerta_Topo'] != "")].copy()
            
            if not df_eventos.empty:
                # Ordenar cronologicamente para calcular a amplitude dos cruzamentos corretamente
                df_eventos = df_eventos.sort_index(ascending=True)
                
                # Criar coluna auxiliar para calcular amplitude acumulada entre cruzamentos de sinal
                df_eventos['Preco_Anterior_Sinal'] = np.where(df_eventos['Sinal'].isin(["🟢 CRUZAMENTO COMPRA", "🔴 CRUZAMENTO VENDA"]), df_eventos['Close'].shift(1), np.nan)
                
                # Preenche temporariamente para calcular apenas nos cruzamentos
                df_cruz_temp = df_eventos[df_eventos['Sinal'].isin(["🟢 CRUZAMENTO COMPRA", "🔴 CRUZAMENTO VENDA"])].copy()
                df_cruz_temp['Preco_Anterior_Sinal'] = df_cruz_temp['Close'].shift(1)
                df_cruz_temp['Amplitude Ciclo (%)'] = (((df_cruz_temp['Close'] - df_cruz_temp['Preco_Anterior_Sinal']) / df_cruz_temp['Preco_Anterior_Sinal']) * 100).round(2)
                df_cruz_temp['Amplitude Ciclo (%)'] = df_cruz_temp['Amplitude Ciclo (%)'].apply(
                    lambda x: f"+{x}%" if pd.notnull(x) and x > 0 else (f"{x}%" if pd.notnull(x) else "-")
                )
                
                # Reinsere a coluna no dataframe principal
                df_eventos['Amplitude Ciclo (%)'] = "-"
                df_eventos.update(df_cruz_temp[['Amplitude Ciclo (%)']])
                
                # Opção de ordenação para visualização
                ordem_exibicao = st.radio("Ordenar histórico de eventos:", options=["Mais recentes primeiro", "Mais antigos primeiro"], horizontal=True)
                if ordem_exibicao == "Mais recentes primeiro":
                    df_eventos = df_eventos.sort_index(ascending=False)
                else:
                    df_eventos = df_eventos.sort_index(ascending=True)
                
                df_mostrar = df_eventos[['Close', 'Amplitude Ciclo (%)', 'MA_500', 'Donchian_Mid', 'Estado_Canal', 'Sinal', 'Alerta_Fundo', 'Alerta_Topo']].round(2)
                st.dataframe(df_mostrar, use_container_width=True, height=450)
                
                st.caption("ℹ️ *A coluna 'Amplitude Ciclo (%)' calcula a variação acumulada entre cruzamentos de sinal, enquanto os alertas indicam os toques nas extremidades do Canal de Donchian.*")
            else:
                st.warning("Nenhum evento relevante registado no período selecionado para este ativo.")
    else:
        st.error("Nenhum dado retornado para o ativo selecionado.")
