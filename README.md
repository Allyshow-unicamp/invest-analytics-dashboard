# Invest Analytics — risco visível, decisões fundamentadas

[![Quality checks](https://github.com/Allyshow-unicamp/invest-analytics-dashboard/actions/workflows/ci.yml/badge.svg)](https://github.com/Allyshow-unicamp/invest-analytics-dashboard/actions/workflows/ci.yml)
![Python 3.14](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-FF4B4B?logo=streamlit&logoColor=white)
![Plotly](https://img.shields.io/badge/Charts-Plotly-38D6BD)
![Quality](https://img.shields.io/badge/Quality-pytest%20%7C%20Ruff%20%7C%20mypy-38D6BD)
![Demo offline](https://img.shields.io/badge/Demo-offline_available-38D6BD)

**Um workspace de pesquisa de investimentos que transforma cotações e dividendos em comparações auditáveis de risco e retorno.**

O projeto nasceu de um motor Python que calculava alocações e publicava resultados em planilhas. A evolução concentra a análise em uma aplicação Streamlit: premissas editáveis, gráficos interativos, regras financeiras isoladas e validação automatizada.

![Dashboard em modo de demonstração, com dados sintéticos](docs/dashboard.jpg)

## O problema de negócio

Um saldo maior pode refletir novos aportes, sem indicar uma estratégia melhor. Um dividend yield elevado também não responde quanto risco o investidor assumiu. Decisões de alocação exigem comparar o retorno com os fluxos, as perdas e as premissas que o produziram.

O Invest Analytics permite investigar essas perguntas em uma única interface:

- **Desempenho:** patrimônio e retorno acumulado livre de aportes, com comparação entre Radar Bazin, DCA, índice e caixa.
- **Risco:** CAGR, volatilidade anualizada, Sharpe, drawdown máximo, VaR e CVaR históricos de 95% por mês.
- **Diversificação:** correlação dos retornos totais e nuvem de carteiras simuladas sem alavancagem.
- **Cenários:** bootstrap histórico com capital atual, aportes futuros e bandas de percentis.
- **Dividendos:** Radar Bazin com cinco anos completos de histórico e calculadoras de valuation por yield, Gordon e renda em USD.
- **Mercados separados:** ativos brasileiros em BRL e americanos em USD, com benchmarks e referências próprios.

## Execute localmente

**Requisito:** Python 3.14 de 64 bits. Dependências diretas fixadas em `requirements.txt`; ferramentas de desenvolvimento em `requirements-dev.txt`.

Windows / PowerShell, na pasta do projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

Se a política local não permitir ativar scripts, use o interpretador do ambiente diretamente:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Linux / macOS:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run app.py
```

Abra [localhost:8501](http://localhost:8501). A aplicação inicia em **Demonstração**, com dados sintéticos reproduzíveis de 2010 a 2025. O uso cotidiano da demonstração não depende de internet, credenciais, CSVs ou planilhas; a instalação inicial de pacotes exige acesso ao registro Python.

Para dados reais, selecione **Mercado (Yahoo + BCB)** na barra lateral, escolha ativos e período e clique em **Analisar carteira**. Somente meses encerrados são usados. A data inicial indica o mês da posição inicial; os retornos começam no intervalo seguinte. O botão **Atualizar dados de mercado** invalida o cache em memória.

## Uma demonstração para avaliação técnica

1. Abra o modo offline e compare Radar Bazin, DCA e caixa com os mesmos aportes.
2. Alterne entre patrimônio e retorno acumulado: os gráficos mostram a diferença entre dinheiro aportado e rentabilidade.
3. Inspecione drawdown, distribuição de perdas e correlação para contextualizar o retorno.
4. Altere o horizonte de cenários e observe a dispersão dos resultados possíveis.
5. Consulte **Metodologia** para revisar as hipóteses antes de interpretar os indicadores.

Os resultados da demonstração são cenários sintéticos, sem relação com a performance histórica dos tickers exibidos.

## Arquitetura e manutenção

```text
invest-analytics-dashboard/
├── app.py                       # Entry point
├── core/
│   ├── metrics.py               # Retorno, risco e caudas históricas
│   ├── portfolio.py             # Posições, fluxos, carteiras e bootstrap
│   ├── bazin.py                 # Sinais e alocação de novos recursos
│   └── valuation.py             # DYT, Gordon e renda parametrizada
├── data/
│   ├── models.py                # MarketData e contrato MarketProvider
│   ├── fetcher.py               # Adaptador Yahoo/BCB e limpeza
│   ├── cache.py                 # Cache TTL genérico e limitado
│   └── demo.py                  # Fonte sintética determinística
├── services/
│   ├── analytics.py             # Caso de uso da comparação
│   └── logging_config.py        # Logs JSON
├── ui/
│   ├── dashboard.py             # Composição e entradas Streamlit
│   ├── components.py            # Cards, tabelas e metodologia
│   └── charts.py                # Figuras Plotly
├── tests/                       # Testes unitários, contratos e AppTest
├── docs/                        # Migração, publicação e captura da UI
├── .github/workflows/ci.yml     # Lint, formatação, tipos e testes
├── .streamlit/config.toml       # Tema e preferências da aplicação
├── requirements.txt
├── requirements-dev.txt
└── pyproject.toml
```

```mermaid
flowchart LR
    App[app.py] --> UI[ui / Streamlit + Plotly]
    UI --> Service[services / casos de uso]
    Service --> Core[core / modelos financeiros]
    UI --> Port[data / MarketProvider]
    Port --> Yahoo[YahooBCBProvider]
    Port --> Demo[DemoProvider]
    Yahoo --> Cache[TTLCache]
    Yahoo --> APIs[Yahoo Finance + SGS BCB]
```

| Decisão | Benefício e limite prático |
| --- | --- |
| Domínio sem Streamlit, rede ou arquivos | Fórmulas e simulação podem ser testadas e usadas em um serviço HTTP ou processamento em lote. |
| `MarketProvider` como `Protocol` | Substitui a fonte por um provedor licenciado sem modificar o motor de carteiras. |
| Serviço de análise separado | Centraliza janelas, moedas, fluxos e referências da comparação. |
| Cache TTL de uma hora, máximo de 16 entradas | Evita downloads repetidos, copia objetos para isolar mutações e não armazena falhas. É local ao processo; múltiplas réplicas pedem cache distribuído. |
| Retornos e matrizes com NumPy/pandas | Simulação de alocações vetorizada; posições mensais mantêm um loop explícito para auditoria dos fluxos. |
| Nuvem amostral, sem otimizador adicional | Dependências enxutas e interpretação honesta: as amostras não representam uma fronteira eficiente exata. |
| Logs JSON e erros de domínio | Facilita diagnóstico de indisponibilidade e qualidade de dados sem depender da interface. |
| Dados sintéticos determinísticos | Demonstrações e testes funcionam sem rate limits ou respostas mutáveis de APIs. |

A separação aplica responsabilidade única e inversão de dependência na fronteira de ingestão, sem criar camadas de abstração para cada fórmula. Detalhes da transição estão em [docs/MIGRATION.md](docs/MIGRATION.md).

## Convenções financeiras

Todas as taxas internas são frações: `0.01` representa 1%. A frequência do dashboard é mensal.

| Indicador | Definição adotada |
| --- | --- |
| Retorno por intervalo | `V_antes_do_aporte / V_anterior - 1`; a primeira linha representa a posição inicial. |
| Retorno acumulado | `produto(1 + r) - 1`. |
| CAGR | `produto(1 + r) ** (12 / n) - 1`. |
| Volatilidade anual | `std(r, ddof=1) * sqrt(12)`. |
| Sharpe anual | `mean(r - rf_mensal) / std(r - rf_mensal, ddof=1) * sqrt(12)`. |
| Drawdown | Cota acumulada dividida pelo pico, incluindo a cota inicial 1, menos 1. |
| VaR 95% mensal | `max(0, -quantile(r, 0.05))`, com interpolação linear. |
| CVaR 95% mensal | Perda média das observações iguais ou inferiores ao quantil; limitada inferiormente a zero. |
| DPA ponderado | Soma dos DPAs dos cinco anos anteriores com pesos 1, 2, 3, 4 e 5, dividida por 15. |

O Sharpe segue a definição baseada em retornos diferenciais discutida por [William F. Sharpe](https://stanford.edu/~wfsharpe/art/sr/sr.htm). A anualização por raiz do tempo é uma convenção que pode ser inadequada sob autocorrelação. Métricas sem base estatística suficiente aparecem como `—`.

**Fluxos comparáveis.** O capital entra no fechamento inicial; cada intervalo seguinte recebe um aporte de fim de mês. Retornos são calculados antes desse aporte. Dividendos são creditados sobre posições anteriores. O fluxo inicial não recebe um aporte mensal extra. Sem capital inicial, períodos sem base de patrimônio ficam sem retorno mensurável.

**Dados e proventos.** `auto_adjust=False` é explícito no download. O backtest usa `Close` e dividendos separados; correlação e alocações usam `Adj Close`, sem somar proventos novamente. O adaptador assume a base de desdobramentos fornecida pelo Yahoo; não multiplica posições por splits novamente. A [documentação do yfinance](https://ranaroussi.github.io/yfinance/reference/api/yfinance.download.html) descreve os parâmetros e a data final exclusiva, convertida pelo adaptador a partir da data inclusiva da interface.

**Referências.** O CDI diário SGS 12 é composto por mês. Falta de CDI não vira retorno zero. O [Ibovespa é um índice de retorno total em reais](https://www.b3.com.br/pt_br/market-data-e-indices/indices/indices-amplos/ibovespa.htm); seus dividendos não são adicionados novamente. Nos EUA, o benchmark é SPY ajustado e o Sharpe usa uma taxa anual efetiva USD informada pelo usuário; caixa USD rende 0% neste modelo.

## Qualidade dos dados e limites

- Datas são ordenadas, duplicatas da resposta diária são consolidadas e meses incompletos são excluídos.
- A janela de preços usa a interseção dos históricos dos ativos e benchmark. O recorte é informado. Lacunas mensais internas, preços não positivos e valores não finitos bloqueiam o estudo.
- Nenhum preço é preenchido com dados futuros. Meses com variação acima de 50% são sinalizados e preservados, pois remover crises distorceria o risco.
- O Radar exige cinco anos completos por ativo. Ano sem proventos é zero; mês sem informação impede o sinal. O histórico de aquecimento é preservado fora da janela de simulação.
- Falha de dados reais gera uma mensagem de erro e permite nova tentativa. O modo sintético é uma escolha explícita, sem substituição automática da fonte.
- Dividendos são aproximados pela data ex e agregados mensalmente. Reinvestimento e sinais de fechamento simplificam a execução real. O Radar não liquida posições por ficarem caras.
- Custos, tributação, slippage, lotes, falências e alterações históricas do universo não são modelados. A cesta atual carrega viés de sobrevivência.
- O bootstrap assume meses independentes. As bandas não são previsão nem probabilidade calibrada de desempenho futuro.
- Yahoo/BCB podem limitar consultas ou corrigir históricos. O software não oferece SLA de dados de mercado. Revise os termos das fontes antes de qualquer redistribuição comercial.

## Testes e integração contínua

```powershell
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m ruff format --check .
python -m mypy
python -m pytest
```

A suíte cobre perdas iniciais, fluxos iguais entre estratégias, base zero de patrimônio, reinvestimento, aquecimento do Radar, ausência de lookahead no DPA, percentuais do CDI, formatos do Yahoo, lacunas, TTL e isolamento do cache. Os testes Streamlit verificam a interface, a troca de mercado, carteira vazia, valores zerados e falhas da fonte. Não fazem requisições externas.

O workflow **Quality checks** executa as mesmas verificações no GitHub Actions com Python 3.14. Os pins são de dependências diretas; dependências transitivas seguem os intervalos dos fornecedores. Para uma implantação com reprodutibilidade binária, gere um lock completo no ambiente de destino.

## Publicação no GitHub

A sequência completa em PowerShell, com Conventional Commits e `gh repo create --public`, está em **[docs/PUBLISH.md](docs/PUBLISH.md)**.

O código novo não precisa de Google Sheets nem de chave de serviço. O `.gitignore` exclui credenciais, caches, ambientes e o legado local. Os arquivos antigos foram mantidos como referência, fora da distribuição pública. Os CSVs antigos não são consumidos: não existe metadado confiável indicando se seus preços já incorporam proventos, e somá-los novamente poderia duplicar o retorno.

Esta ferramenta apoia pesquisa e avaliação de hipóteses de investimento. Nenhum resultado constitui garantia de retorno ou recomendação individual.
