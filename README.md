# Dochian — Scanner Donchian (305) & Ciclos

App Streamlit (`setup_donchian.py`) com o Donchian 305 e as médias 500/610 em candles de 5m da brapi.

## O que tem
- **Scanner** da watchlist com estado do canal, alinhamento, **zona de indecisão / rompimento** e colunas do Kronos.
- **Gráfico interativo**: candles, canal, Mid, MA500/610, cruzamentos (▲▼), rompimentos (★) e faixas amarelas na zona de indecisão. No painel de baixo fica a distância Mid × MA500. Quando há previsão, mostra também a banda do Kronos.
- **Validação dos sinais**: compara o que aconteceu 1h, 4h e ~1 pregão depois de cada evento com uma entrada aleatória no mesmo sentido. Mede acerto, retorno e movimento máximo a favor e contra.
- Limiares da zona e do rompimento ajustáveis na barra lateral.

## Zona de indecisão e rompimento
- `Dist_Rel = (Mid − MA500) / (topo − fundo do canal)`.
- **Zona**: `|Dist_Rel|` abaixo do limiar. É quando o Mid fica colado na média e gera sinais para os dois lados.
- **Rompimento**: primeiro candle em que `|Dist_Rel|` passa do limiar de rompimento, desde que o ativo tenha estado na zona nos últimos N candles.

## Kronos (opcional, automático)
O workflow `.github/workflows/kronos.yml` roda o `kronos_job.py` em dias úteis às 18:17 (Brasília) e grava `data/kronos_*.csv`. O app só lê esses arquivos, sem PyTorch no Streamlit.

Para ativar:
1. Em **Settings → Secrets and variables → Actions → New repository secret**, crie `BRAPI_TOKEN`.
2. Em **Actions → Kronos diário → Run workflow**, faça a primeira execução.

Colunas no app:
- **amplitude ÷ ATR**: > 1 indica mais volatilidade prevista que o normal.
- **prob. alta**.
- **🔥 Zona + expansão prevista**: o ativo está na zona e o Kronos espera expansão (≥ 1,2× o ATR).
