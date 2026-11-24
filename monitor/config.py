"""Configuração do monitor do Rio Doce em Governador Valadares.

Fontes dos números:
- Cotas de alerta/inundação: Boletins do SAH Doce (SGB/CPRM), tabela de cotas de referência.
- Tempos de viagem: correlação cruzada de vazões horárias da telemetria ANA em 6 cheias
  (jan/2020, mar/2020, jan/2022, dez/2022, jan/2023, jan/2025, jan/2026) — mediana, em horas.
- Curva cota-vazão de Valadares: ajuste H = a + b*Q^c sobre telemetria ANA 2024-2026
  (RMSE 0,9 cm no período do ajuste; nos picos de 2020–2026 erra de 0 a +9 cm,
  porque a curva-chave oficial muda entre anos — tende a superestimar levemente).
"""
import os

TZ = "America/Sao_Paulo"

# Estação de referência (régua oficial usada pela Defesa Civil)
GV = {"cod": "56850000", "nome": "Governador Valadares", "lat": -18.8831, "lon": -41.9508,
      "alerta": 320, "inundacao": 360}

# Cota (na régua de GV) em que a água chega na rua do usuário. Calibrar com o histórico
# de cheias — ver README. Pode ser sobrescrita pela variável de ambiente RUA_CM.
RUA_CM = int(os.environ["RUA_CM"]) if os.environ.get("RUA_CM", "").strip() else None

# Postos a montante: código ANA, cotas SGB (quando o posto integra o SAH Doce) e
# tempo médio de viagem da onda até Valadares (h).
MONTANTE = [
    {"cod": "56661000", "nome": "Nova Era (rio Piracicaba)", "alerta": 350, "inundacao": 470, "lag_h": 36},
    {"cod": "56110005", "nome": "Ponte Nova (rio Piranga)", "alerta": 280, "inundacao": 330, "lag_h": 30},
    {"cod": "56696000", "nome": "Mário de Carvalho (rio Piracicaba)", "alerta": 540, "inundacao": 620, "lag_h": 30},
    {"cod": "56825000", "nome": "Naque Velho (rio Santo Antônio)", "alerta": 640, "inundacao": 740, "lag_h": 20},
    {"cod": "56719998", "nome": "Belo Oriente (rio Doce)", "alerta": 860, "inundacao": 900, "lag_h": 11},
    {"cod": "56846200", "nome": "UHE Baguari – jusante", "alerta": None, "inundacao": None, "lag_h": 2.5},
]

# Curva cota-vazão de Valadares (cm a partir de m³/s)
CURVA = {"a": 31.1398, "b": 5.1108, "c": 0.5485}

# Pontos para chuva prevista (aprox. centro de cada sub-bacia que alimenta Valadares)
SUBBACIAS_CHUVA = [
    {"nome": "Piranga (cabeceira)", "lat": -20.42, "lon": -42.92},
    {"nome": "Piracicaba", "lat": -19.72, "lon": -43.12},
    {"nome": "Santo Antônio", "lat": -19.05, "lon": -42.90},
    {"nome": "Doce médio (Ipatinga–Belo Oriente)", "lat": -19.40, "lon": -42.45},
    {"nome": "Valadares (local)", "lat": -18.88, "lon": -41.95},
]

# Gatilhos de alerta
SUBIDA_RAPIDA_CM_H = 5.0      # média em 3h; p99 histórico acima de 250 cm é ~7,9 cm/h
NIVEL_MIN_SUBIDA = 250        # só alarma subida rápida a partir deste nível
DADO_VELHO_H = 3              # sem leitura de GV há mais que isso → aviso de dado ausente
HORA_RELATORIO = 7            # relatório diário (hora local)

STATE_PATH = os.environ.get("STATE_PATH", "data/state.json")
LOG_CSV = os.environ.get("LOG_CSV", "data/leituras_gv.csv")
