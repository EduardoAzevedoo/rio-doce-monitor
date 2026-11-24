"""Previsão do nível em Governador Valadares (6h a 120h) com faixa de incerteza calibrada.

Modelo: gradient boosting quantílico (P10/P50/P90) por horizonte, treinado com a telemetria
ANA de 7 temporadas chuvosas (2019–2026) e chuva por sub-bacia. Faixas recalibradas pelos
erros fora da amostra (CQR). Validação: ver README, seção "Previsão".
"""
from __future__ import annotations
import datetime as dt
import gzip
import json
import os
import pickle
import time
import urllib.request

import numpy as np
import pandas as pd

from . import config as C
from . import features as F

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR_MODELOS = os.path.join(RAIZ, "modelos")
_PONTOS = {"piranga": (-20.42, -42.92), "piracicaba": (-19.72, -43.12),
           "santoantonio": (-19.05, -42.90), "docemedio": (-19.40, -42.45), "gv": (-18.88, -41.95)}


def _carregar():
    with gzip.open(os.path.join(DIR_MODELOS, "modelo_gv.pkl.gz"), "rb") as f:
        modelos = pickle.load(f)
    with open(os.path.join(DIR_MODELOS, "meta.json")) as f:
        meta = json.load(f)
    return modelos, meta


def chuva_horaria():
    """Chuva horária (mm) por sub-bacia: 3 dias passados + 6 dias de previsão (hora local)."""
    lat = ",".join(str(v[0]) for v in _PONTOS.values())
    lon = ",".join(str(v[1]) for v in _PONTOS.values())
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
           "&hourly=precipitation&past_days=3&forecast_days=6&timezone=America%2FSao_Paulo")
    req = urllib.request.Request(url, headers={"User-Agent": "rio-doce-monitor/1.0"})
    erro = None
    for i in range(4):
        try:
            data = json.loads(urllib.request.urlopen(req, timeout=60).read())
            break
        except Exception as e:  # 503/timeout transitórios do Open-Meteo
            erro = e
            time.sleep(10 * (i + 1))
    else:
        raise RuntimeError(f"chuva prevista indisponível: {erro}")
    out = {}
    for nome, d in zip(_PONTOS, data):
        out[f"r_{nome}"] = pd.Series(d["hourly"]["precipitation"], index=pd.to_datetime(d["hourly"]["time"]))
    return pd.DataFrame(out)


def _serie(registros, campo):
    s = pd.Series({r["t"]: r[campo] for r in registros if r[campo] is not None}, dtype=float)
    if s.empty:
        return s
    s.index = pd.to_datetime(s.index)
    return s.sort_index().resample("1h").mean()


def prever(gv_registros, montante, chuva=None):
    """Retorna dict com hora de emissão e lista de previsões por horizonte, ou None.

    gv_registros: lista de dicts da ANA (Valadares); montante: lista de (config_posto, registros)."""
    modelos, meta = _carregar()
    chuva = chuva if chuva is not None else chuva_horaria()
    gv_h = F.limpar(_serie(gv_registros, "nivel_cm"), 40)
    if gv_h.dropna().empty:
        return None
    t0 = gv_h.dropna().index.max()
    idx = pd.date_range(t0 - pd.Timedelta(hours=72), t0 + pd.Timedelta(hours=125), freq="1h")
    df = pd.DataFrame(index=idx)
    df["gv_h"] = gv_h.reindex(idx)
    df["gv_q"] = F.limpar(_serie(gv_registros, "vazao_m3s"), 800).reindex(idx)
    por_cod = {p["cod"]: s for p, s in montante}
    for k, cod in F.POSTOS.items():
        s = _serie(por_cod.get(cod, []), "vazao_m3s")
        df[f"q_{k}"] = F.limpar(s, 1500).reindex(idx) if not s.empty else np.nan
    for c in chuva.columns:
        df[c] = chuva[c].reindex(idx)
    X = F.montar(df)
    linha = X.loc[[t0], meta["features"]]
    h0 = float(linha["gv_h"].iloc[0])
    prev = []
    for H in meta["horizontes"]:
        p = np.sort([modelos[H][q].predict(linha)[0] for q in meta["quantis"]])
        p10, p50, p90 = h0 + p[0], h0 + p[1], h0 + p[2]
        reg = "alto" if (h0 >= 280 or p90 >= 300) else "normal"
        o = meta["offsets_cqr_cm"][f"{H}|{reg}"]
        prev.append({"H": H, "valido": (t0 + pd.Timedelta(hours=H)).to_pydatetime(),
                     "p50": p50, "baixo": p10 - o, "alto": p90 + o})
    return {"emitida": t0.to_pydatetime(), "h0": h0, "prev": prev,
            "chuva_futura_bacia_mm": float(X.loc[t0, [f"rb_f{k}" for k in range(1, 6)]].sum())}
