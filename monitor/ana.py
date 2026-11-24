"""Cliente da telemetria pública da ANA (HidroTelemetria / ServiceANA.asmx)."""
from __future__ import annotations
import datetime as dt
import time
import urllib.request
import xml.etree.ElementTree as ET

BASE = "https://telemetriaws1.ana.gov.br/ServiceANA.asmx/DadosHidrometeorologicos"


def _f(x):
    try:
        return float(x) if x not in (None, "") else None
    except ValueError:
        return None


def fetch(cod: str, inicio: dt.date, fim: dt.date, retries: int = 3, timeout: int = 120):
    """Retorna lista de dicts {t, nivel_cm, vazao_m3s, chuva_mm} ordenada por tempo.

    Horários da ANA estão em hora local de Brasília (UTC-3)."""
    url = f"{BASE}?codEstacao={cod}&DataInicio={inicio:%d/%m/%Y}&DataFim={fim:%d/%m/%Y}"
    last = None
    for i in range(retries):
        try:
            raw = urllib.request.urlopen(url, timeout=timeout).read()
            break
        except Exception as e:  # rede instável no SNIRH é comum
            last = e
            time.sleep(5 * (i + 1))
    else:
        raise RuntimeError(f"ANA {cod}: falha após {retries} tentativas: {last}")
    root = ET.fromstring(raw)
    out = []
    for el in root.iter("DadosHidrometereologicos"):
        t = (el.findtext("DataHora") or "").strip()
        if not t:
            continue
        try:
            ts = dt.datetime.strptime(t, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        out.append({
            "t": ts,
            "nivel_cm": _f(el.findtext("Nivel")),
            "vazao_m3s": _f(el.findtext("Vazao")),
            "chuva_mm": _f(el.findtext("Chuva")),
        })
    out.sort(key=lambda r: r["t"])
    return out
