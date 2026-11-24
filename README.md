# Monitor do Rio Doce — Governador Valadares (Esplanadinha)

Agente que checa o Rio Doce **de hora em hora** (rodada leve; completa com previsão a cada 3h, ou toda hora com rio ≥ 280 cm) e manda pelo Telegram:

- **Relatório diário (~7h):** nível em Valadares, tendência, postos rio acima com tempo de chegada, chuva prevista na bacia (7 dias) e cenário indicativo de 5 dias.
- **Alertas imediatos:** mudança de faixa (com histerese de 10 cm), subida rápida (≥ 5 cm/h em 3h, a partir de 250 cm), posto a montante passando da cota SGB, boletim novo do SGB, telemetria parada, cenário de 5 dias acima da inundação.
- **Autodiagnóstico:** avisa se o próprio monitor falhar 2, 6 ou 24 vezes seguidas. O GitHub também manda e-mail quando um workflow falha.

## Fontes

| Fonte | Uso | Status validado em 23/11/2026 |
|---|---|---|
| Telemetria ANA (`telemetriaws1.ana.gov.br`) | Nível e vazão a cada 15 min em Valadares (56850000) e 6 postos a montante | ✅ atraso típico 15–60 min |
| SGB/SACE — SAH Doce (`sace.sgb.gov.br/doce`) | Detecta boletim novo (oficial) | ✅ responde; nenhum boletim publicado ainda na operação 2026/27 |
| Open-Meteo Forecast | Chuva prevista por sub-bacia (7 dias) | ✅ |
| Open-Meteo Flood (GloFAS v4) | Vazão prevista (ensemble) → convertida em cota | ✅ — **experimental, sem validação** (fase 3) |

## Números de referência (derivados dos dados da ANA, 2019–2026)

**Tempo médio da onda até Valadares:** Nova Era ~36h · Ponte Nova ~30h · Mário de Carvalho ~30h · Naque Velho ~20h · Belo Oriente ~11h · UHE Baguari ~2,5h.

**Curva cota-vazão (Valadares):** `H(cm) = 31,14 + 5,111·Q^0,5485` — RMSE 0,9 cm em 2024–2026. Nos picos históricos erra de 0 a +9 cm (2022: 606 → 606; 2023: 513 → 518; mar/2020: 436 → 445) — viés conservador, superestima um pouco.

**Picos acima de 320 cm na régua de Valadares:**

| Data | Pico (cm) |
|---|---|
| 27/01/2020 | 583 |
| 06/03/2020 | 436 |
| 23/02/2021 | 367 |
| **11/01/2022** | **606** |
| 13/02/2022 | 408 |
| 23/12/2022 | 416 |
| **09/01/2023** | **513** |
| 28/01/2023 | 402 |
| 26/01/2024 | 356 |
| 14/01/2025 | 376 |
| 25/01/2026 | 367 |

**Backtest dos alertas de nível** (replay hora a hora com dados reais): 1º aviso antes de passar de 360 cm — jan/2020: 38h · jan/2022: 41h · jan/2023: 114h · jan/2026: 42h.

## Previsão 6h–120h (fase 3)

Modelo de *gradient boosting* quantílico (P10/P50/P90), um por horizonte (6, 12, 24, 36, 48, 72, 96, 120h), treinado com a telemetria ANA horária de 7 temporadas chuvosas (out–abr, 2019/20 a 2025/26) e com chuva por sub-bacia (Piranga, Piracicaba, Santo Antônio, Doce médio). Entradas: nível e tendência em Valadares, vazão e tendência em Nova Era, Ponte Nova, Mário de Carvalho, Naque Velho e Baguari, chuva das últimas 24/72h e **chuva prevista** para os próximos 5 dias. As faixas foram recalibradas pelos erros reais fora da amostra (CQR), mirando 80% de cobertura (85% com água alta).

### Validação

**1. Temporada de fora (leave-one-season-out, chuva observada)** — cada temporada prevista por um modelo que não a viu. Erro médio absoluto (cm), com água alta (≥300 cm):

| Horizonte | 6h | 12h | 24h | 36h | 48h | 72h | 96h | 120h |
|---|---|---|---|---|---|---|---|---|
| Modelo | 7 | 11 | 17 | 22 | 26 | 35 | 38 | 40 |
| Persistência (rio parado) | 11 | 20 | 36 | 51 | 64 | 82 | 95 | 103 |

Picos previstos sem o modelo ter visto a cheia: jan/2022 (604 cm) — 72h antes, com o rio em 308, previu 492 [359–547]; jan/2023 (512) — 48h antes previu 521; jan/2026 (367) — 48h antes, rio em 263, previu 352 [304–383]. **Falha conhecida:** subestima a cheia mais extrema da série (jan/2020, 583 cm: 24h antes previu 504).

**2. Teste honesto (treino até abr/2024; teste 2024/25 e 2025/26 com a chuva que estava PREVISTA na época)** — água alta: erro de 15 cm em 24h e 31 cm em 72h (persistência: 28 e 59). Faixa calibrada cobriu 70–87% dos casos. Cheia de jan/2026: o modelo indicou possível água na rua em 18/01, com o rio a ~150 cm, 6 dias antes de a água chegar (24/01). Dez/2024: indicou possível água na rua; o rio chegou a 340 cm (1 cm abaixo).

### Como os alertas usam a previsão (máquina de estados)
- ⚠️ **Possível água na sua rua**: faixa pessimista ≥ 341 cm em até 72h.
- 🚨 **Água provável na sua rua**: previsão central ≥ 341 cm em até 72h.
- Só avisa quando a situação **piora**: sobe de estado, pico previsto +15 cm, ou chegada da água a menos de 24h.
- ✅ **Risco diminuiu**: só depois de 24h seguidas com a previsão pessimista abaixo de 326 cm (evita "liberar" numa oscilação da previsão de chuva).
- 96h e 120h aparecem só no boletim, marcados como baixa confiança.

**Replay das duas últimas temporadas** (modelo treinado até 2024, chuva prevista arquivada, lógica de alerta completa a cada 3h):

| Temporada | Água na rua (real) | 1º "provável" | Avisos de rua na temporada | Sem água na rua em 96h |
|---|---|---|---|---|
| 2024/25 | 13/01 (376 cm) | 131h antes (rio em 303) | 13 | dez/24 (304 cm); 28–31/12 chegou a 340 (1 cm abaixo) |
| 2025/26 | 24/01 (367 cm) | 77h antes (rio em 158) | 11 | 05/01 (274), 24/02 (298), 13/03 (284) |

Versão anterior da regra (repetição a cada 12h) gerava 37 e 20 avisos e um falso "risco diminuiu" em 22/01/2026, dois dias antes de a água chegar — corrigido.

### Limites
- Poucas cheias grandes no histórico (3 acima de 500 cm): previsões acima de ~520 cm tendem a subestimar.
- Treino usou chuva de reanálise (ERA5); em operação a chuva passada vem da análise do modelo de previsão — diferença pequena, não medida.
- Manobras de usinas não programadas não são previstas; aparecem em ~2–3h via posto de Baguari.
- Retreinar ao fim de cada temporada: `treino/` (baixar → base → cv → teste_honesto → treinar).

## Instalação (uma vez, ~10 min)

1. **Bot do Telegram:** no Telegram, fale com `@BotFather` → `/newbot` → guarde o token.
2. **Seu chat_id:** mande qualquer mensagem para o seu bot e abra `https://api.telegram.org/bot<TOKEN>/getUpdates` — o número em `"chat":{"id": ...}` é o chat_id.
3. **Secrets no GitHub:** neste repositório → *Settings → Secrets and variables → Actions → New repository secret*:
   - `TELEGRAM_BOT_TOKEN` = token do passo 1
   - `TELEGRAM_CHAT_ID` = número do passo 2
4. **Calibração da rua** (já feita, padrão no código): a água começa a chegar na rua com ~341 cm na régua de Valadares; lâmina ≈ 0,49 × (cota − 341) cm. Para ajustar sem mexer no código, crie em *Variables* `RUA_CM`.
5. **Testar:** *Actions → Monitor Rio Doce → Run workflow*. O relatório chega no Telegram em ~1 min.

## Uso local

```bash
python -m monitor.run --dry-run --relatorio   # imprime o relatório, não envia nada
```

Dependências em `requirements.txt` (numpy, scipy, pandas, scikit-learn — versões fixadas para carregar o modelo).

## Limites (leia)

- A régua é a da estação de Valadares. A tradução para a sua rua vem de 3 cheias observadas (2022: ~1,3 m a 606 cm; 2025: acima do meio-fio a 376 cm; 2026: abaixo do meio-fio a 367 cm) — erro esperado ±10 cm. Anote o que observar em cada cheia para refinar.
- O cenário de 5 dias é indicativo: depende de chuva que ainda não caiu e ainda não foi validado contra cheias passadas.
- O agente **complementa** a Defesa Civil (199) e o alerta por SMS (CEP para 40199). Não substitui.
