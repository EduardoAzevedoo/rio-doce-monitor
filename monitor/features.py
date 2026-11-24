"""Variáveis do modelo de previsão — mesmo código no treino e na operação.

Entrada: DataFrame horário (índice = hora local) com colunas:
  gv_h  nível em Governador Valadares (cm)
  gv_q  vazão em Governador Valadares (m³/s)
  q_<posto>  vazão nos postos a montante (m³/s): ne, pn, mc, nv, bj
  r_<sub>  chuva horária (mm) por sub-bacia: piranga, piracicaba, santoantonio, docemedio, gv
           — no passado é chuva observada/analisada; no futuro é chuva PREVISTA.
Saída: DataFrame de variáveis, uma linha por hora de emissão.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

POSTOS = {"ne": "56661000", "pn": "56110005", "mc": "56696000", "nv": "56825000", "bj": "56846200"}
SUBS = ["piranga", "piracicaba", "santoantonio", "docemedio"]
HORIZONTES = [6, 12, 24, 36, 48, 72, 96, 120]


def limpar(s: pd.Series, max_salto: float) -> pd.Series:
    """Remove leituras espúrias (saltos isolados) e interpola buracos curtos (≤3h)."""
    s = s.copy()
    med = s.rolling(7, center=True, min_periods=3).median()
    s[(s - med).abs() > max_salto] = np.nan
    return s.interpolate(limit=3, limit_area="inside")


def _soma_futura(r: pd.Series, ini_h: int, fim_h: int) -> pd.Series:
    # chuva acumulada entre t+ini_h e t+fim_h (exclusive t)
    c = r.fillna(0).cumsum()
    return c.shift(-fim_h) - c.shift(-ini_h)


def _soma_passada(r: pd.Series, h: int) -> pd.Series:
    return r.fillna(0).rolling(h, min_periods=1).sum()


def montar(df: pd.DataFrame) -> pd.DataFrame:
    X = pd.DataFrame(index=df.index)
    h = df["gv_h"]
    X["gv_h"] = h
    for lag in (3, 12, 24, 48):
        X[f"gv_d{lag}"] = h - h.shift(lag)
    X["gv_q"] = df["gv_q"]
    for p in POSTOS:
        q = df.get(f"q_{p}")
        if q is None:
            q = pd.Series(np.nan, index=df.index)
        X[f"q_{p}"] = q
        X[f"q_{p}_d6"] = q - q.shift(6)
        X[f"q_{p}_d24"] = q - q.shift(24)
    # chuva passada (observada)
    bacia = df[[f"r_{s}" for s in SUBS]].mean(axis=1)
    for s in SUBS:
        X[f"r_{s}_p24"] = _soma_passada(df[f"r_{s}"], 24)
        X[f"r_{s}_p72"] = _soma_passada(df[f"r_{s}"], 72)
    X["r_gv_p24"] = _soma_passada(df["r_gv"], 24)
    # chuva futura (prevista) por blocos de 24h
    for k in range(1, 6):
        ini, fim = 24 * (k - 1), 24 * k
        X[f"rb_f{k}"] = _soma_futura(bacia, ini, fim)
        mx = pd.concat([_soma_futura(df[f"r_{s}"], ini, fim) for s in SUBS], axis=1)
        X[f"rmax_f{k}"] = mx.max(axis=1)
        if k <= 3:
            for s in SUBS:
                X[f"r_{s}_f{k}"] = mx.iloc[:, SUBS.index(s)]
    X["mes"] = X.index.month
    return X


def alvo(df: pd.DataFrame, horizonte: int) -> pd.Series:
    return df["gv_h"].shift(-horizonte) - df["gv_h"]
