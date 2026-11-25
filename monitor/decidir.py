"""Decide se a rodada agendada é completa (com previsão) ou leve (só leituras e alertas).

Completa quando: não é agendada (manual/código novo); hora local múltipla de 3; relatório diário
pendente; rio ≥ 280 cm; última completa há mais de 3,5h (agendamentos descartados); ou sem leitura.
Só usa a biblioteca padrão — roda antes de instalar dependências.
"""
import datetime as dt
import json
import os
import sys
from zoneinfo import ZoneInfo

from . import ana, config as C


def decidir(evento: str) -> tuple[bool, str]:
    agora = dt.datetime.now(ZoneInfo(C.TZ)).replace(tzinfo=None)
    if evento != "schedule":
        return True, f"evento {evento}"
    try:
        st = json.load(open(C.STATE_PATH))
    except (FileNotFoundError, ValueError):
        return True, "sem estado"
    if agora.hour % 3 == 0:
        return True, "hora múltipla de 3"
    if agora.hour >= C.HORA_RELATORIO and st.get("relatorio_dia") != agora.date().isoformat():
        return True, "relatório diário pendente"
    ult = st.get("ultima_completa")
    if not ult or (agora - dt.datetime.fromisoformat(ult)).total_seconds() > 3.5 * 3600:
        return True, "última completa há mais de 3,5h"
    try:
        s = [r for r in ana.fetch(C.GV["cod"], (agora - dt.timedelta(days=1)).date(), agora.date(),
                                  retries=2, timeout=60) if r["nivel_cm"]]
    except Exception:
        return True, "sem leitura da ANA"
    if not s:
        return True, "sem leitura da ANA"
    if s[-1]["nivel_cm"] >= 280:
        return True, f"rio em {s[-1]['nivel_cm']:.0f} cm (≥280)"
    return False, f"rio em {s[-1]['nivel_cm']:.0f} cm, rodada leve"


if __name__ == "__main__":
    evento = os.environ.get("GITHUB_EVENT_NAME", "manual")
    if evento == "workflow_dispatch" and os.environ.get("AGENDADO", "").lower() == "true":
        evento = "schedule"  # chamada do agendador externo: mesma regra da rodada agendada
    completo, motivo = decidir(evento)
    print(f"completo={'true' if completo else 'false'} ({motivo})")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"completo={'true' if completo else 'false'}\n")
    sys.exit(0)
