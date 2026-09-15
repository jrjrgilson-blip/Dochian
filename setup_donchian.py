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
    # Aumentámos para 3 meses para garantir milhares de velas!
    url = "https://brapi.dev/api/quote/BOVA11?range=3mo&interval=5m"
    headers = {"Authorization": f"Bearer {BRAPI_TOKEN}"}
    
    try:
        resp = requests.get(url, headers=headers).json()
        if 'results' in resp:
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

df = carregar_dados_teste()

if not df.empty:
    st.info(f"📊 Foram carregados **{len(df)}** candles de 5 minutos da base de dados da Brapi.")
    
    if len(df) < 610:
        st.error("⚠️ Atenção: O histórico tem menos de 610 velas. As médias móveis não vão aparecer por falta de tempo gráfico.")
    
    with st.spinner("A processar a matemática estrutural (Donchian + Médias)..."):
        # 1. As Médias Móveis Estruturais
        df['MA_500'] = df['Close'].rolling(window=500).mean()
        df['MA_610'] = df['Close'].rolling(window=610).mean()
        
        # 2. O Canal de Donchian (305)
        df['Donchian_Upper'] = df['High'].rolling(window=305).max()
        df['Donchian_Lower'] = df['Low'].rolling(window=305).min()
        df['Donchian_Mid'] = (df['Donchian_Upper'] + df['Donchian_Lower']) / 2
        
        # 3. Regras e Sinais (Usando lógica matemática estruturada à prova de erros)
        df['Sinal'] = "Aguardar"
        df['Alerta_Fundo'] = ""
        
        # Variáveis do candle anterior (para detetar o cruzamento exato)
        donch_mid_prev = df['Donchian_Mid'].shift(1)
        ma_500_prev = df['MA_500'].shift(1)
        
        # Condição de Compra (Cruza para cima)
        compra_mask = (df['Donchian_Mid'] > df['MA_500']) & (donch_mid_prev <= ma_500_prev)
        df.loc[compra_mask, 'Sinal'] = "🟢 COMPRA"
        
        # Condição de Venda (Cruza para baixo)
        venda_mask = (df['Donchian_Mid'] < df['MA_500']) & (donch_mid_prev >= ma_500_prev)
        df.loc[venda_mask, 'Sinal'] = "🔴 VENDA"
        
        # Alerta de Toque no Fundo da Estrutura
        alerta_mask = (df['Low'] <= df['Donchian_Lower']) & (df['Close'] < df['MA_500'])
        df.loc[alerta_mask, 'Alerta_Fundo'] = "⚠️ Tocou Fundo"

        # --- PLOTAGEM DO GRÁFICO ---
        fig = go.Figure()

        # Preço (Candles)
        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="Preço"))
        
        # Médias Móveis
        fig.add_trace(go.Scatter(x=df.index, y=df['MA_500'], line=dict(color='yellow', width=2), name='MA 500'))
        fig.add_trace(go.Scatter(x=df.index, y=df['MA_610'], line=dict(color='orange', width=2), name='MA 610'))
        
        # Canal de Donchian
        fig.add_trace(go.Scatter(x=df.index, y=df['Donchian_Upper'], line=dict(color='rgba(255,255,255,0.3)', width=1, dash='dot'), name='Topo Canal'))
        fig.add_trace(go.Scatter(x=df.index, y=df['Donchian_Lower'], line=dict(color='rgba(255,255,255,0.3)', width=1, dash='dot'), name='Fundo Canal', fill='tonexty', fillcolor='rgba(128,128,128,0.1)'))
        fig.add_trace(go.Scatter(x=df.index, y=df['Donchian_Mid'], line=dict(color='cyan', width=2), name='Média Canal'))

        fig.update_layout(
            title="Mapeamento Institucional: BOVA11 (5 Minutos)", 
            xaxis_rangeslider_visible=False, 
            height=650, 
            template="plotly_dark",
            margin=dict(l=10, r=10, b=10, t=40)
        )
        
        st.plotly_chart(fig, use_container_width=True)

        # --- TABELA DE SINAIS ---
        st.subheader("📋 Registro de Cruzamentos e Alertas")
        
        # Filtra a tabela para mostrar apenas os momentos em que algo aconteceu
        df_sinais = df[(df['Sinal'] != "Aguardar") | (df['Alerta_Fundo'] != "")].copy()
        
        if not df_sinais.empty:
            df_sinais = df_sinais.sort_index(ascending=False).head(20) # Mostra os 20 alertas mais recentes
            df_mostrar = df_sinais[['Close', 'MA_500', 'Donchian_Mid', 'Donchian_Lower', 'Sinal', 'Alerta_Fundo']].round(2)
            st.dataframe(df_mostrar, use_container_width=True)
        else:
            st.warning("O histórico foi carregado, mas nenhum cruzamento ocorreu neste período.")
else:
    st.error("Nenhum dado foi retornado. Verifique a chave da API ou a conexão com a Brapi.")
