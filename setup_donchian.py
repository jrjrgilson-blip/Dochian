import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go

st.set_page_config(page_title="Backtest Donchian", layout="wide")
st.title("🔬 Laboratório de Teste: Donchian (305) x Médias (500, 610)")

# Acesso ao cofre do Streamlit
try:
    BRAPI_TOKEN = st.secrets["BRAPI_TOKEN"]
except:
    st.error("Chave não encontrada no secrets.")
    st.stop()

st.write("Ativo de espelho (Mini Índice): **BOVA11** | Tempo: **5 Minutos**")

@st.cache_data(ttl=300)
def carregar_dados_teste():
    # Pedimos 1 mês de dados para garantir que temos as 610 velas necessárias para a média longa
    url = "https://brapi.dev/api/quote/BOVA11?range=1mo&interval=5m"
    headers = {"Authorization": f"Bearer {BRAPI_TOKEN}"}
    
    resp = requests.get(url, headers=headers).json()
    if 'results' in resp:
        hist = resp['results'][0].get('historicalDataPrice', [])
        df = pd.DataFrame(hist)
        df['Date'] = pd.to_datetime(df['date'], unit='s')
        df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
        df.set_index('Date', inplace=True)
        return df
    return pd.DataFrame()

df = carregar_dados_teste()

if not df.empty:
    with st.spinner("A processar a matemática estrutural (Donchian + Médias)..."):
        # 1. As Médias Móveis Estruturais
        df['MA_500'] = df['Close'].rolling(window=500).mean()
        df['MA_610'] = df['Close'].rolling(window=610).mean()
        
        # 2. O Canal de Donchian (305)
        df['Donchian_Upper'] = df['High'].rolling(window=305).max()
        df['Donchian_Lower'] = df['Low'].rolling(window=305).min()
        df['Donchian_Mid'] = (df['Donchian_Upper'] + df['Donchian_Lower']) / 2
        
        # Removemos o período inicial vazio (onde as médias ainda estão a ser calculadas)
        df = df.dropna()
        
        # 3. Regras e Sinais (A sua Tese)
        df['Sinal'] = "Aguardar"
        df['Alerta_Fundo'] = ""
        
        for i in range(1, len(df)):
            # Condição de Compra: Média do Canal cruza MA 500 para cima
            if df['Donchian_Mid'].iloc[i] > df['MA_500'].iloc[i] and df['Donchian_Mid'].iloc[i-1] <= df['MA_500'].iloc[i-1]:
                df.iloc[i, df.columns.get_loc('Sinal')] = "🟢 COMPRA"
                
            # Condição de Venda: Média do Canal cruza MA 500 para baixo
            elif df['Donchian_Mid'].iloc[i] < df['MA_500'].iloc[i] and df['Donchian_Mid'].iloc[i-1] >= df['MA_500'].iloc[i-1]:
                df.iloc[i, df.columns.get_loc('Sinal')] = "🔴 VENDA"
                
            # Alerta de Toque no Fundo (A armadilha)
            if df['Low'].iloc[i] <= df['Donchian_Lower'].iloc[i] and df['Close'].iloc[i] < df['MA_500'].iloc[i]:
                df.iloc[i, df.columns.get_loc('Alerta_Fundo')] = "⚠️ Tocou Fundo"

        # --- PLOTAGEM DO GRÁFICO (Para validação visual do padrão) ---
        fig = go.Figure()

        # Preço (Candles)
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="Preço"))
        
        # Médias Móveis
        fig.add_trace(go.Scatter(x=df.index, y=df['MA_500'], line=dict(color='yellow', width=2), name='MA 500'))
        fig.add_trace(go.Scatter(x=df.index, y=df['MA_610'], line=dict(color='orange', width=2), name='MA 610'))
        
        # Canal de Donchian
        fig.add_trace(go.Scatter(x=df.index, y=df['Donchian_Upper'], line=dict(color='rgba(255,255,255,0.3)', width=1, dash='dot'), name='Topo Canal'))
        fig.add_trace(go.Scatter(x=df.index, y=df['Donchian_Lower'], line=dict(color='rgba(255,255,255,0.3)', width=1, dash='dot'), name='Fundo Canal', fill='tonexty', fillcolor='rgba(128,128,128,0.1)'))
        fig.add_trace(go.Scatter(x=df.index, y=df['Donchian_Mid'], line=dict(color='cyan', width=2), name='Média do Canal'))

        fig.update_layout(title="Mapeamento Institucional: BOVA11 (5 Minutos)", xaxis_rangeslider_visible=False, height=600, template="plotly_dark")
        
        st.plotly_chart(fig, use_container_width=True)

        # --- TABELA DE SINAIS ---
        st.subheader("📋 Registro de Cruzamentos e Alertas")
        df_sinais = df[(df['Sinal'] != "Aguardar") | (df['Alerta_Fundo'] != "")].copy()
        
        if not df_sinais.empty:
            df_sinais = df_sinais.sort_index(ascending=False).head(20) # Mostra os últimos 20 eventos
            df_mostrar = df_sinais[['Close', 'MA_500', 'Donchian_Mid', 'Donchian_Lower', 'Sinal', 'Alerta_Fundo']].round(2)
            st.dataframe(df_mostrar, use_container_width=True)
        else:
            st.info("Nenhum sinal ou alerta acionado no período analisado.")
else:
    st.error("Erro ao carregar dados. Verifique a API.")
