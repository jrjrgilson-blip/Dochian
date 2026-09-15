import streamlit as st
import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go

st.set_page_config(page_title="Backtest Donchian Avançado", layout="wide")
st.title("🔬 Laboratório Institucional: Donchian (305) & Análise de Extremidades")

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
    options=["5 Dias", "15 Dias", "1 Mês", "3 Meses"], 
    index=2
)

mapa_periodos = {
    "5 Dias": "5d",
    "15 Dias": "15d",
    "1 Mês": "1mo",
    "3 Meses": "3mo"
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
    st.info(f"📊 Foram carregados **{len(df)}** candles de 5 minutos para o ativo {ativo_escolhido}.")
    
    if len(df) < 610:
        st.warning(f"⚠️ Atenção: O histórico tem apenas {len(df)} velas. A média móvel de 610 períodos precisa de mais dados para aparecer.")
    
    with st.spinner("A processar a matemática estrutural (Donchian, Médias e Extremidades)..."):
        # 1. As Médias Móveis Estruturais
        df['MA_500'] = df['Close'].rolling(window=500).mean()
        df['MA_610'] = df['Close'].rolling(window=610).mean()
        
        # 2. O Canal de Donchian (305)
        df['Donchian_Upper'] = df['High'].rolling(window=305).max()
        df['Donchian_Lower'] = df['Low'].rolling(window=305).min()
        df['Donchian_Mid'] = (df['Donchian_Upper'] + df['Donchian_Lower']) / 2
        
        # 3. Análise de Extremidades do Canal (Novas Máximas e Mínimas)
        # Compara o topo/fundo atual com o de 10 candles atrás para ver a inclinação das extremidades
        df['Upper_Slope'] = df['Donchian_Upper'].diff(10)
        df['Lower_Slope'] = df['Donchian_Lower'].diff(10)
        
        df['Estado_Canal'] = "Lateral / Compressão ⚖️"
        # Se o topo sobe e o fundo também sobe -> Expansão de Alta
        exp_alta = (df['Upper_Slope'] > 0) & (df['Lower_Slope'] > 0)
        # Se o topo desce e o fundo também desce -> Expansão de Baixa
        exp_baixa = (df['Upper_Slope'] < 0) & (df['Lower_Slope'] < 0)
        # Se o canal está a abrir (topo sobe, fundo desce) -> Alargamento de Volatilidade
        alargamento = (df['Upper_Slope'] > 0) & (df['Lower_Slope'] < 0)
        # Se o canal está a fechar (topo desce, fundo sobe) -> Estreitamento / Squeeze
        estreitamento = (df['Upper_Slope'] < 0) & (df['Lower_Slope'] > 0)
        
        df.loc[exp_alta, 'Estado_Canal'] = "📈 Expansão de Alta (Novas Máximas)"
        df.loc[exp_baixa, 'Estado_Canal'] = "📉 Expansão de Baixa (Novas Mínimas)"
        df.loc[alargamento, 'Estado_Canal'] = "🌊 Alargamento de Volatilidade"
        df.loc[estreitamento, 'Estado_Canal'] = "🤏 Estreitamento (Squeeze)"

        # 4. Regras e Sinais
        df['Sinal'] = "Aguardar"
        df['Alerta_Fundo'] = ""
        
        donch_mid_prev = df['Donchian_Mid'].shift(1)
        ma_500_prev = df['MA_500'].shift(1)
        
        compra_mask = (df['Donchian_Mid'] > df['MA_500']) & (donch_mid_prev <= ma_500_prev)
        df.loc[compra_mask, 'Sinal'] = "🟢 COMPRA"
        
        venda_mask = (df['Donchian_Mid'] < df['MA_500']) & (donch_mid_prev >= ma_500_prev)
        df.loc[venda_mask, 'Sinal'] = "🔴 VENDA"
        
        alerta_mask = (df['Low'] <= df['Donchian_Lower']) & (df['Close'] < df['MA_500'])
        df.loc[alerta_mask, 'Alerta_Fundo'] = "⚠️ Tocou Fundo"

        # --- MÉTRICA DO MOMENTO ATUAL (Última vela) ---
        ultimo_estado = df['Estado_Canal'].iloc[-1]
        st.metric(label="🧭 Diagnóstico Atual da Estrutura do Canal (Donchian 305)", value=ultimo_estado)

        # --- PLOTAGEM DO GRÁFICO ---
        fig = go.Figure()

        fig.add_trace(go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="Preço"))
        fig.add_trace(go.Scatter(x=df.index, y=df['MA_500'], line=dict(color='yellow', width=2), name='MA 500'))
        fig.add_trace(go.Scatter(x=df.index, y=df['MA_610'], line=dict(color='orange', width=2), name='MA 610'))
        
        fig.add_trace(go.Scatter(x=df.index, y=df['Donchian_Upper'], line=dict(color='rgba(0,255,255,0.5)', width=1, dash='dot'), name='Topo Canal'))
        fig.add_trace(go.Scatter(x=df.index, y=df['Donchian_Lower'], line=dict(color='rgba(255,0,0,0.5)', width=1, dash='dot'), name='Fundo Canal', fill='tonexty', fillcolor='rgba(128,128,128,0.1)'))
        fig.add_trace(go.Scatter(x=df.index, y=df['Donchian_Mid'], line=dict(color='cyan', width=2), name='Média Canal'))

        fig.update_layout(
            title=f"Análise Estrutural de Extremidades: {ativo_escolhido} (5 Minutos)", 
            xaxis_rangeslider_visible=False, 
            height=650, 
            template="plotly_dark",
            margin=dict(l=10, r=10, b=10, t=40)
        )
        
        st.plotly_chart(fig, use_container_width=True)

        # --- TABELA DE SINAIS E ESTADOS ---
        st.subheader("📋 Registo de Sinais e Dinâmica do Canal")
        
        df_sinais = df[(df['Sinal'] != "Aguardar") | (df['Alerta_Fundo'] != "")].copy()
        
        if not df_sinais.empty:
            df_sinais = df_sinais.sort_index(ascending=False).head(20)
            df_mostrar = df_sinais[['Close', 'MA_500', 'Donchian_Mid', 'Donchian_Lower', 'Estado_Canal', 'Sinal', 'Alerta_Fundo']].round(2)
            st.dataframe(df_mostrar, use_container_width=True)
        else:
            st.warning("Nenhum cruzamento ou toque no fundo registado no intervalo selecionado.")
else:
    st.error("Nenhum dado retornado para o ativo ou período selecionado.")
