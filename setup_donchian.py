import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go

st.set_page_config(page_title="Laboratório Donchian Institucional", layout="wide")
st.title("🔬 Laboratório Institucional: Donchian (305) & Diagnóstico de Momento")

# Acesso ao cofre do Streamlit
try:
    BRAPI_TOKEN = st.secrets["BRAPI_TOKEN"]
except:
    st.error("Chave não encontrada no secrets.")
    st.stop()

# --- PAINEL LATERAL DE CONTROLO ---
st.sidebar.header("⚙️ Parâmetros de Visualização")
ativo_escolhido = st.sidebar.text_input("Ativo de Leitura:", value="BOVA11").upper()

opcao_periodo = st.sidebar.selectbox(
    "Quantidade de Histórico (5m):", 
    options=["1 Mês", "3 Meses", "6 Meses (Máximo API)"], 
    index=2
)

mapa_periodos = {
    "1 Mês": "1mo",
    "3 Meses": "3mo",
    "6 Meses (Máximo API)": "6mo"
}
range_api = mapa_periodos[opcao_periodo]

st.write(f"Ativo Monitorizado: **{ativo_escolhido}** | Tempo Gráfico: **5 Minutos** | Período: **{opcao_periodo}**")

@st.cache_data(ttl=300)
def carregar_dados_teste(ticker, range_val, token):
    url = f"https://brapi.dev/api/quote/{ticker}?range={range_val}&interval=5m"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        resp = requests.get(url, headers=headers).json()
        if 'results' in resp and resp['results']:
            hist = resp['results'][0].get('historicalDataPrice', [])
            df = pd.DataFrame(hist)
            if not df.empty:
                df['Date'] = pd.to_datetime(df['date'], unit='s')
                df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
                df.set_index('Date', inplace=True)
                return df
    except Exception as e:
        pass
    return pd.DataFrame()

df = carregar_dados_teste(ativo_escolhido, range_api, BRAPI_TOKEN)

if not df.empty:
    st.info(f"📊 Foram carregados **{len(df)}** candles de 5 minutos para o ativo {ativo_escolhido} (Período: {df.index[0].strftime('%d/%m/%Y')} até {df.index[-1].strftime('%d/%m/%Y')}).")
    
    if len(df) < 610:
        st.warning(f"⚠️ Atenção: O histórico tem apenas {len(df)} velas. A média móvel de 610 períodos precisa de mais dados.")
    
    with st.spinner("A processar a matemática estrutural..."):
        # 1. As Médias Móveis Estruturais
        df['MA_500'] = df['Close'].rolling(window=500).mean()
        df['MA_610'] = df['Close'].rolling(window=610).mean()
        
        # 2. O Canal de Donchian (305)
        df['Donchian_Upper'] = df['High'].rolling(window=305).max()
        df['Donchian_Lower'] = df['Low'].rolling(window=305).min()
        df['Donchian_Mid'] = (df['Donchian_Upper'] + df['Donchian_Lower']) / 2
        
        # 3. Análise de Extremidades do Canal
        df['Upper_Slope'] = df['Donchian_Upper'].diff(10)
        df['Lower_Slope'] = df['Donchian_Lower'].diff(10)
        
        df['Estado_Canal'] = "Lateral / Compressão ⚖️"
        exp_alta = (df['Upper_Slope'] > 0) & (df['Lower_Slope'] > 0)
        exp_baixa = (df['Upper_Slope'] < 0) & (df['Lower_Slope'] < 0)
        alargamento = (df['Upper_Slope'] > 0) & (df['Lower_Slope'] < 0)
        estreitamento = (df['Upper_Slope'] < 0) & (df['Lower_Slope'] > 0)
        
        df.loc[exp_alta, 'Estado_Canal'] = "📈 Expansão de Alta (Novas Máximas)"
        df.loc[exp_baixa, 'Estado_Canal'] = "📉 Expansão de Baixa (Novas Mínimas)"
        df.loc[alargamento, 'Estado_Canal'] = "🌊 Alargamento de Volatilidade"
        df.loc[estreitamento, 'Estado_Canal'] = "🤏 Estreitamento (Squeeze)"

        # 4. Regras, Sinais e Diagnóstico (Com janela otimizada para capturar os pivôs)
        df['Sinal'] = "Aguardar"
        df['Alerta_Fundo'] = ""
        df['Alerta_Topo'] = ""
        
        donch_mid_prev = df['Donchian_Mid'].shift(3) # Janela de 3 candles para maior assertividade no cruzamento
        ma_500_prev = df['MA_500'].shift(3)
        
        compra_mask = (df['Donchian_Mid'] > df['MA_500']) & (donch_mid_prev <= ma_500_prev)
        df.loc[compra_mask, 'Sinal'] = "🟢 CRUZAMENTO COMPRA"
        
        venda_mask = (df['Donchian_Mid'] < df['MA_500']) & (donch_mid_prev >= ma_500_prev)
        df.loc[venda_mask, 'Sinal'] = "🔴 CRUZAMENTO VENDA"
        
        alerta_fundo_mask = (df['Low'] <= df['Donchian_Lower']) & (df['Close'] < df['MA_500'])
        df.loc[alerta_fundo_mask, 'Alerta_Fundo'] = "⚠️ Tocou Fundo / Exaustão"

        alerta_topo_mask = (df['High'] >= df['Donchian_Upper']) & (df['Close'] > df['MA_500'])
        df.loc[alerta_topo_mask, 'Alerta_Topo'] = "🎯 Tocou Topo / Alvo"

        # --- PAINEL DE DIAGNÓSTICO DO MOMENTO ATUAL ---
        ult_close = df['Close'].iloc[-1]
        ult_ma500 = df['MA_500'].iloc[-1]
        ult_ma610 = df['MA_610'].iloc[-1]
        ult_mid = df['Donchian_Mid'].iloc[-1]
        ult_estado = df['Estado_Canal'].iloc[-1]
        
        medias_alinhadas_alta = (ult_mid > ult_ma500) and (ult_ma500 > ult_ma610)
        medias_alinhadas_baixa = (ult_mid < ult_ma500) and (ult_ma500 < ult_ma610)

        st.markdown("### 🎯 Diagnóstico do Momento Atual (Último Candle)")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(label="Dinâmica do Canal (Donchian)", value=ult_estado)
            
        with col2:
            if medias_alinhadas_alta:
                st.metric(label="Alinhamento Estrutural", value="🟢 Altista Perfeito")
            elif medias_alinhadas_baixa:
                st.metric(label="Alinhamento Estrutural", value="🔴 Baixista Perfeito")
            else:
                st.metric(label="Alinhamento Estrutural", value="⚖️ Transição / Emaranhado")
                
        with col3:
            if ult_close > ult_ma500 and "Expansão de Alta" in ult_estado:
                st.metric(label="Leitura Tática", value="🚀 Continuidade de Alta")
            elif ult_close < ult_ma500 and "Expansão de Baixa" in ult_estado:
                st.metric(label="Leitura Tática", value="🩸 Continuidade de Baixa")
            else:
                st.metric(label="Leitura Tática", value="🔍 Zona de Observação")

        st.divider()

        # --- PLOTAGEM DO GRÁFICO ---
        fig = go.Figure()

        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="Preço"))
        fig.add_trace(go.Scatter(x=df.index, y=df['MA_500'], line=dict(color='yellow', width=2), name='MA 500'))
        fig.add_trace(go.Scatter(x=df.index, y=df['MA_610'], line=dict(color='orange', width=2), name='MA 610'))
        
        fig.add_trace(go.Scatter(x=df.index, y=df['Donchian_Upper'], line=dict(color='rgba(0,255,255,0.5)', width=1, dash='dot'), name='Topo Canal'))
        fig.add_trace(go.Scatter(x=df.index, y=df['Donchian_Lower'], line=dict(color='rgba(255,0,0,0.5)', width=1, dash='dot'), name='Fundo Canal', fill='tonexty', fillcolor='rgba(128,128,128,0.1)'))
        fig.add_trace(go.Scatter(x=df.index, y=df['Donchian_Mid'], line=dict(color='cyan', width=2), name='Média Canal'))

        fig.update_layout(
            title=f"Mapeamento Institucional: {ativo_escolhido} (5 Minutos)", 
            xaxis_rangeslider_visible=False, 
            height=650, 
            template="plotly_dark",
            margin=dict(l=10, r=10, b=10, t=40)
        )
        
        st.plotly_chart(fig, use_container_width=True)

        # --- TABELA DE EVENTOS (Ampliada e com seletor de ordem) ---
        st.subheader("📋 Registo Histórico de Sinais e Eventos Estruturais")
        
        df_eventos = df[(df['Sinal'] != "Aguardar") | (df['Alerta_Fundo'] != "") | (df['Alerta_Topo'] != "")].copy()
        
        if not df_eventos.empty:
            # Filtro para o utilizador escolher se quer ver do mais recente ou do mais antigo
            ordem_exibicao = st.radio("Ordenar histórico de eventos:", options=["Mais recentes primeiro", "Mais antigos primeiro"], horizontal=True)
            
            if ordem_exibicao == "Mais recentes primeiro":
                df_eventos = df_eventos.sort_index(ascending=False)
            else:
                df_eventos = df_eventos.sort_index(ascending=True)
                
            # Mostramos mais linhas para abranger agosto inteiro
            df_mostrar = df_eventos[['Close', 'MA_500', 'Donchian_Mid', 'Estado_Canal', 'Sinal', 'Alerta_Fundo', 'Alerta_Topo']].round(2)
            st.dataframe(df_mostrar, use_container_width=True, height=400)
        else:
            st.warning("Nenhum evento relevante registado no período selecionado.")
else:
    st.error("Nenhum dado retornado para o ativo ou período selecionado.")
