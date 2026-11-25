"""Diagnóstico de saúde do monitor para o sinal de vida (Healthchecks.io).

Lê o estado gravado e imprime os problemas; sai com 0 (saudável) ou 1 (degradado).
O workflow manda "sucesso" ou "falha" ao Healthchecks com esse resultado. Assim, além de
"o monitor não rodou", o serviço externo também alerta quando ele roda mas está cego ou mudo.
Só biblioteca padrão.
"""
import datetime as dt
import json
import sys
from zoneinfo import ZoneInfo

from . import config as C


def problemas(st: dict, agora: dt.datetime) -> list[str]:
    p = []
    if st.get("falha_envio"):
        p.append(f"Telegram falhando ({st['falha_envio']}x seguidas) — alertas não estão chegando")
    if st.get("falha_consecutiva"):
        p.append(f"monitor com erro ({st['falha_consecutiva']}x seguidas)")
    if st.get("aviso_dado_velho"):
        p.append("telemetria da ANA sem dado novo há mais de 3h — monitor cego")
    if (st.get("previsao_falhas") or 0) >= 3:
        p.append(f"previsão indisponível em {st['previsao_falhas']} rodadas completas seguidas")
    ult = st.get("ultima_execucao")
    if not ult or (agora - dt.datetime.fromisoformat(ult)).total_seconds() > 2 * 3600:
        p.append("o estado não foi atualizado nesta rodada")
    if agora.hour >= C.HORA_RELATORIO + 2 and st.get("relatorio_dia") != agora.date().isoformat():
        p.append("boletim diário de hoje não foi enviado")
    return p


if __name__ == "__main__":
    agora = dt.datetime.now(ZoneInfo(C.TZ)).replace(tzinfo=None)
    try:
        st = json.load(open(C.STATE_PATH))
    except (FileNotFoundError, ValueError):
        print("estado ausente ou ilegível")
        sys.exit(1)
    pr = problemas(st, agora)
    print("; ".join(pr) if pr else "ok")
    sys.exit(1 if pr else 0)
