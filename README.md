# Monitor do Rio Doce — Governador Valadares (Esplanadinha)

Agente que checa o Rio Doce **de hora em hora** e manda pelo Telegram:

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

**Backtest dos alertas** (replay hora a hora com dados reais): 1º aviso antes de passar de 360 cm — jan/2020: 38h · jan/2022: 41h · jan/2023: 114h · jan/2026: 42h.

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

Sem dependências externas (só biblioteca padrão do Python 3.10+).

## Limites (leia)

- A régua é a da estação de Valadares. A tradução para a sua rua vem de 3 cheias observadas (2022: ~1,3 m a 606 cm; 2025: acima do meio-fio a 376 cm; 2026: abaixo do meio-fio a 367 cm) — erro esperado ±10 cm. Anote o que observar em cada cheia para refinar.
- O cenário de 5 dias é indicativo: depende de chuva que ainda não caiu e ainda não foi validado contra cheias passadas.
- O agente **complementa** a Defesa Civil (199) e o alerta por SMS (CEP para 40199). Não substitui.
