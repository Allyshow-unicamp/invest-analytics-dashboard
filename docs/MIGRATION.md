# Do motor de planilhas ao workspace de pesquisa

Foram lidos os nove arquivos Python presentes no diretório original, incluindo subpastas.

| Arquivo legado | Responsabilidade identificada | Destino da refatoração |
| --- | --- | --- |
| `motor_investimentos_v6.py` | Execução monolítica, planilhas B3/EUA, fórmulas de valuation e renda | `core/bazin.py`, `core/valuation.py`, `services/analytics.py` e `ui/` |
| `motorcore/__init__.py` | Exportações do núcleo compartilhado | Pacotes `core`, `data`, `services`, `ui` com fronteiras explícitas |
| `motorcore/bazin.py` | Sinais, backtest, benchmarks, métricas e bootstrap | `core/bazin.py`, `core/portfolio.py`, `core/metrics.py` |
| `motorcore/dados.py` | Yahoo, BCB, CSVs e cache pickle | `data/fetcher.py`, `data/models.py`, `data/cache.py`, `data/demo.py` |
| `motorcore/estudo_eua.py` | DCA e comparação de aristocratas com ETFs | Mesmo backtest modular para ativos EUA em USD, com dados do provedor |
| `motorcore/formatador.py` | Formatação numérica | `ui/components.py` |
| `motorcore/teste_rapido.py` | Smoke test dependente de rede | Testes determinísticos de domínio e contratos em `tests/` |
| `maquina_do_tempo/app.py` | Interface, controles, dados e gráficos acoplados | `app.py`, `ui/`, `services/` |
| `maquina_do_tempo/teste_app.py` | Execução da interface e simulação de falhas | `tests/test_app.py` com AppTest e fontes substituídas |

## Correções que mudam resultados

1. **Aportes:** o legado alocava o primeiro aporte no Radar, mas não no primeiro ponto do Ibovespa. O novo motor tem uma posição inicial e aportes somente ao fim de cada intervalo seguinte para todas as estratégias. O CDI segue essa mesma convenção.
2. **TWR:** a fórmula anterior descontava o aporte do numerador apesar de algumas simulações o investirem antes do retorno. Agora o retorno é medido antes do fluxo externo e a convenção é única.
3. **Drawdown:** patrimônio com aportes mascara perdas. A métrica agora usa a cota de retornos acumulados e inclui o capital inicial no pico, capturando uma primeira queda.
4. **Sharpe:** a diferença entre dois CAGRs dividida pela volatilidade foi substituída pela média dos retornos excedentes dividida por seu desvio-padrão.
5. **Aquecimento Bazin:** o recorte do backtest também eliminava os dividendos anteriores necessários ao sinal. A janela de execução é recortada separadamente do histórico completo de proventos. São exigidos cinco anos-calendário completos, sem normalizar uma janela incompleta como se fosse equivalente.
6. **Dados ausentes:** `bfill()` no índice, cotação ausente valorizada em zero e CDI faltante tratado como 0% foram eliminados do novo fluxo. O sistema valida a janela comum e informa indisponibilidade.
7. **Proventos EUA:** o DCA legado não incluía o capital inicial no acumulado aportado e distribuía o dividendo anual por todos os meses do próprio ano. O novo fluxo usa o mesmo controle de capital das demais estratégias e dividendos mensais da fonte, sem o rateio anual retrospectivo.
8. **Unidades:** o legado dividia novamente por 100 um IPCA 12m já fracionário na interface. O painel novo explicita unidades e não reproduz esse indicador incorretamente; o foco atual é risco/retorno de carteiras.
9. **Conclusões:** textos que atribuíam superioridade ao Radar independentemente dos resultados foram substituídos por métricas observadas e premissas. A interface não declara uma estratégia vencedora por construção.
10. **Gordon:** as premissas agora são editáveis e a fórmula é `D1 / (k - g)`, com validação de `k > g`. Múltiplos e yields estáticos da planilha não são exibidos como dados atuais.

## Preservação e escopo

Os arquivos originais permanecem no disco e estão excluídos da publicação. O aplicativo novo não importa `motorcore`, não executa scripts antigos e não realiza operações em Google Sheets. Não foi necessário abrir ou utilizar o conteúdo do arquivo de credenciais.

O estudo EUA usa os ativos disponíveis no novo provedor. Os CSVs locais antigos não têm documentação da base de ajustes; utilizá-los com dividendos adicionais poderia contar proventos duas vezes. Uma futura importação precisa exigir explicitamente a natureza da série e sua moeda.

Calendários fixos de pagamento, perfis heurísticos de qualidade, múltiplos estáticos e instruções prescritivas da planilha foram retirados. O novo Radar preserva os pesos e tetos de yield, mas a exclusão por variação de preço de cinco anos do monólito não é tratada como análise fundamentalista de deterioração.

As posições mensais e a agregação de eventos são aproximações educacionais. Retornos anteriores e posteriores à refatoração não devem ser considerados equivalentes: as correções de fluxos, dados e estatística alteram os resultados.
