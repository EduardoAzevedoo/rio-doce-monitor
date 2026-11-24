"""Fontes externas além da ANA: Open-Meteo (chuva e GloFAS) e SGB/SACE (boletins)."""
from __future__ import annotations
import hashlib
import json
import re
import urllib.request
import uuid

UA = {"User-Agent": "rio-doce-monitor/1.0 (uso pessoal, alerta de cheia)"}


def _get_json(url, timeout=60, tentativas=4):
    import time
    req = urllib.request.Request(url, headers=UA)
    for i in range(tentativas):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        except Exception:
            if i == tentativas - 1:
                raise
            time.sleep(10 * (i + 1))


def chuva_prevista(pontos, dias=7):
    """Chuva diária prevista (mm) por ponto, modelo best_match do Open-Meteo."""
    lats = ",".join(str(p["lat"]) for p in pontos)
    lons = ",".join(str(p["lon"]) for p in pontos)
    url = ("https://api.open-meteo.com/v1/forecast?latitude=" + lats + "&longitude=" + lons +
           f"&daily=precipitation_sum,precipitation_probability_max&forecast_days={dias}"
           "&timezone=America%2FSao_Paulo")
    data = _get_json(url)
    if isinstance(data, dict):
        data = [data]
    out = []
    for p, d in zip(pontos, data):
        out.append({"nome": p["nome"], "datas": d["daily"]["time"],
                    "mm": d["daily"]["precipitation_sum"],
                    "prob": d["daily"].get("precipitation_probability_max")})
    return out


def glofas(lat, lon, dias=7):
    """Vazão prevista (m³/s) do GloFAS v4 via Open-Meteo Flood API: média e envelope do ensemble."""
    url = (f"https://flood-api.open-meteo.com/v1/flood?latitude={lat}&longitude={lon}"
           "&daily=river_discharge,river_discharge_max,river_discharge_min,river_discharge_p75"
           f"&forecast_days={dias}&past_days=2")
    d = _get_json(url)["daily"]
    return d


def sgb_ultimo_boletim():
    """Consulta o serviço público do SACE (DWR) pelo último boletim do SAH Doce.

    Retorna None quando não há boletim publicado na operação corrente, ou um dict com
    'id' (hash estável do conteúdo), 'nome' e 'data' quando houver."""
    base = "https://sace.sgb.gov.br/doce"
    import http.cookiejar
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    opener.addheaders = list(UA.items())
    opener.open(base, timeout=60).read()
    jsid = next((c.value for c in cj if c.name == "JSESSIONID"), "")  # exigido pelo CSRF do DWR
    body = ("callCount=1\nwindowName=\nc0-scriptName=BoletimService\n"
            "c0-methodName=obtemUltimoBoletim\nc0-id=0\nbatchId=1\ninstanceId=0\n"
            "page=%2Fdoce%2F\n"
            f"httpSessionId={jsid}\n"
            f"scriptSessionId={uuid.uuid4().hex.upper()}/{uuid.uuid4().hex[:7]}\n").encode()
    req = urllib.request.Request(base + "/dwr/call/plaincall/BoletimService.obtemUltimoBoletim.dwr",
                                 data=body, headers={"Content-Type": "text/plain", **UA})
    txt = opener.open(req, timeout=60).read().decode("utf-8", "replace")
    if "handleBatchException" in txt:
        raise RuntimeError("SACE recusou a chamada: " + txt[-300:])
    if "handleException" in txt:
        if "nenhum dado" in txt or "nenhum boletim" in txt.lower():
            return None
        raise RuntimeError("SACE respondeu com erro: " + txt[:300])
    reply = txt.split("//#DWR-REPLY", 1)[-1]
    nome = re.search(r'nome\s*:\s*"([^"]*)"', reply)
    data = re.search(r'dataGeracao\s*:\s*new Date\((\d+)\)', reply)
    return {
        "id": hashlib.sha1(reply.encode()).hexdigest()[:12],
        "nome": (nome.group(1).encode().decode("unicode_escape") if nome else "Boletim SAH Doce"),
        "data_ms": int(data.group(1)) if data else None,
    }
