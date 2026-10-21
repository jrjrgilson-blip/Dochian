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

## Relatório de coerência (sob demanda)
Na **Análise Individual**, o botão **📄 Gerar relatório de coerência** monta o relatório só quando é tocado. Depois aparecem dois downloads:
- **HTML**, que abre no celular ou no PC e inclui:
  - situação atual;
  - qualidade dos dados: buracos, OHLC inconsistente, volume zerado, saltos anormais, atualidade;
  - coerência dos sinais: whipsaw, cruzamentos repetidos, cruzamentos contra a expansão, rompimentos não confirmados;
  - distribuição do tempo por estado do canal;
  - validação contra entrada aleatória;
  - checagens do Kronos;
  - gráfico interativo;
  - registo de eventos.
- **CSV** com os candles e todos os indicadores (`;` e vírgula decimal, abre direto no Excel).

Se os parâmetros ou os dados mudarem, o relatório anterior é invalidado e é preciso gerar de novo.

## Backtest por operação (sem alvo)
O sinal é lido no fecho do candle e executado na abertura do candle seguinte. Comparo duas estratégias:
- **🚀 Rompimento:** entra no ★ e sai quando o Mid volta à zona ou no rompimento contrário.
- **🔁 Todo cruzamento:** fica sempre posicionado e vira a cada cruzamento. Serve para medir o custo de operar a indecisão.

Na barra lateral dá para ajustar:
- stop em múltiplos do ATR (0 = sem stop);
- custo por lado;
- só compra, ou compra e venda.

**Métricas:** acerto, ganho e perda médios, payoff, fator de lucro, resultado composto, drawdown e curva de capital.

**Onde aparece:**
- na Análise Individual, com a curva e a lista de operações;
- no Scanner, uma linha por ativo mais o total;
- no relatório.

## Histórico intradiário acumulado
A brapi só entrega uns 60 dias de dados em 5, 15 ou 60 min. Por isso, o workflow `.github/workflows/historico.yml` roda o `historico_job.py` em dias úteis às 18:43 e guarda os candles de 5 min da watchlist em `data/historico/5m/<ATIVO>/<AAAA-MM>.csv`.

Com **Usar histórico acumulado** ligado, o app:
- junta esse acervo com os dados mais recentes da brapi;
- monta os candles de 15 e 60 min a partir dos de 5 min.

O histórico cresce um pregão por dia.
