"""Monitor do Rio Doce em Governador Valadares.

Uso:
  python -m monitor.run              # modo automático (agendado): checagem + relatório diário às 7h
  python -m monitor.run --relatorio  # força o relatório completo agora
  python -m monitor.run --dry-run    # não envia Telegram nem grava estado; só imprime
"""
from __future__ import annotations
import argparse
import copy
import csv
import datetime as dt
import html
import json
import os
import sys
import traceback
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from . import ana, config as C, fontes

TZ = ZoneInfo(C.TZ)
NIVEIS = [
    (0, "🟢", "Normal"),
    (1, "🟡", "Atenção"),
    (2, "🟠", "ALERTA (≥ 320 cm)"),
    (3, "🔴", "INUNDAÇÃO (≥ 360 cm)"),
    (4, "🚨", "ÁGUA CHEGANDO NA SUA RUA"),
]


def agora():
    return dt.datetime.now(TZ).replace(tzinfo=None)


def faixa(cm):
    if cm is None:
        return None
    if C.RUA_CM and cm >= C.RUA_CM:
        return 4
    if cm >= C.GV["inundacao"]:
        return 3
    if cm >= C.GV["alerta"]:
        return 2
    if cm >= 250:
        return 1
    return 0


HISTERESE_CM = 10


def limite_inferior(f):
    return {1: 250, 2: C.GV["alerta"], 3: C.GV["inundacao"], 4: C.RUA_CM or 10_000}.get(f, 0)


def faixa_com_histerese(cm, anterior):
    """Sobe de faixa na hora; só desce quando o nível fica 10 cm abaixo do limite da faixa atual."""
    f = faixa(cm)
    if f is None or anterior is None or f >= anterior:
        return f
    while anterior > f and cm >= limite_inferior(anterior) - HISTERESE_CM:
        return anterior
    return f


def lamina_rua(cm):
    """Lâmina d'água estimada na rua (cm) para uma cota em GV; 0 se não chega."""
    if not C.RUA_CM or cm is None:
        return 0
    return max(0.0, C.RUA_FATOR * (cm - C.RUA_CM))


def texto_rua(cm):
    if not C.RUA_CM or cm is None:
        return ""
    if cm < C.RUA_CM - C.RUA_AVISO_ANTES_CM:
        return f"Sua rua: sem risco agora (a água começa a chegar com ~{C.RUA_CM} cm na régua)."
    if cm < C.RUA_CM:
        return f"🏠 <b>Sua rua: faltam ~{C.RUA_CM - cm:.0f} cm na régua</b> para a água começar a chegar."
    lam = lamina_rua(cm)
    meio = "acima do meio-fio" if cm >= C.RUA_MEIO_FIO_CM else "abaixo do meio-fio"
    return f"🏠 <b>Sua rua: água estimada ~{lam:.0f} cm ({meio})</b> — estimativa ±10 cm."


def cota_de_vazao(q):
    return C.CURVA["a"] + C.CURVA["b"] * max(q, 0) ** C.CURVA["c"]


def ultimo_valido(serie, campo="nivel_cm"):
    for r in reversed(serie):
        if r[campo] is not None and 0 < r[campo] < 2000:
            return r
    return None


def valor_em(serie, t_alvo, campo="nivel_cm", tol_min=45):
    melhor = None
    for r in serie:
        if r[campo] is None:
            continue
        d = abs((r["t"] - t_alvo).total_seconds()) / 60
        if d <= tol_min and (melhor is None or d < melhor[0]):
            melhor = (d, r[campo])
    return melhor[1] if melhor else None


def carregar_estado():
    try:
        with open(C.STATE_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def salvar_estado(st):
    os.makedirs(os.path.dirname(C.STATE_PATH), exist_ok=True)
    with open(C.STATE_PATH, "w") as f:
        json.dump(st, f, indent=2, ensure_ascii=False, default=str)


def anexar_log(serie, desde):
    os.makedirs(os.path.dirname(C.LOG_CSV), exist_ok=True)
    novo = not os.path.exists(C.LOG_CSV)
    n = 0
    with open(C.LOG_CSV, "a", newline="") as f:
        w = csv.writer(f)
        if novo:
            w.writerow(["datahora_local", "nivel_cm", "vazao_m3s", "chuva_mm"])
        for r in serie:
            if desde and r["t"].isoformat() <= desde:
                continue
            if r["nivel_cm"] is None:
                continue
            w.writerow([r["t"].isoformat(), r["nivel_cm"], r["vazao_m3s"], r["chuva_mm"]])
            n += 1
    return n


def registrar_previsao(pv, falhas):
    """Histórico das previsões emitidas (para verificar o modelo ao longo da temporada)."""
    caminho = os.path.join(os.path.dirname(C.LOG_CSV), "previsoes.csv")
    novo = not os.path.exists(caminho)
    with open(caminho, "a", newline="") as f:
        w = csv.writer(f)
        if novo:
            w.writerow(["emitida", "nivel_atual_cm", "horizonte_h", "valido_para", "p50_cm", "baixo_cm", "alto_cm", "status"])
        if not pv:
            motivo = "; ".join(x for x in falhas if "previs" in x or "chuva" in x or "ANA Valadares" in x)
            w.writerow([agora().isoformat(timespec="minutes"), "", "", "", "", "", "",
                        "indisponivel: " + (motivo or "sem leituras de Valadares")[:200]])
            return
        for p in pv["prev"]:
            w.writerow([pv["emitida"].isoformat(timespec="minutes"), round(pv["h0"], 1), p["H"],
                        p["valido"].isoformat(timespec="minutes"), round(p["p50"], 1),
                        round(p["baixo"], 1), round(p["alto"], 1), "ok"])


def enviar_telegram(texto, dry):
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if dry or not token or not chat:
        print("----- MENSAGEM (não enviada) -----\n" + texto + "\n----------------------------------")
        return False
    for i in range(0, len(texto), 3900):
        data = urllib.parse.urlencode({"chat_id": chat, "text": texto[i:i + 3900], "parse_mode": "HTML",
                                       "disable_web_page_preview": "true"}).encode()
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data, timeout=30).read()
    return True


# ------------------------------------------------------------------ coleta

_NOMES_SUB = {"r_piranga": "Piranga (cabeceira)", "r_piracicaba": "Piracicaba", "r_santoantonio": "Santo Antônio",
              "r_docemedio": "Doce médio (Ipatinga–Belo Oriente)", "r_gv": "Valadares (local)"}


def _chuva_diaria(ch, t):
    """Converte a chuva horária (mm) em totais diários a partir de hoje, no formato do relatório."""
    d = ch[ch.index.date >= t.date()].resample("1D").sum(min_count=1)
    datas = [x.date().isoformat() for x in d.index][:7]
    return [{"nome": _NOMES_SUB[c], "datas": datas, "mm": [None if v != v else float(v) for v in d[c].values[:7]]}
            for c in ch.columns]


def coletar(leve=False):
    t = agora()
    ini, fim = (t - dt.timedelta(days=3)).date(), t.date()
    falhas, dados = [], {}
    # Todos os postos em paralelo, com tempo limitado: com a ANA lenta, a coleta sequencial
    # (7 postos × 3 tentativas × 120 s) estourava o limite do job (rodada de 25/11 11h).
    from concurrent.futures import ThreadPoolExecutor, wait
    postos = [("gv", C.GV)] + [(p["cod"], p) for p in C.MONTANTE]
    ex = ThreadPoolExecutor(max_workers=len(postos))
    futs = {k: ex.submit(ana.fetch, p["cod"], ini, fim, 2, 45) for k, p in postos}
    wait(list(futs.values()), timeout=150)
    ex.shutdown(wait=False, cancel_futures=True)
    res = {}
    for k, p in postos:
        f = futs[k]
        nome = "Valadares" if k == "gv" else p["nome"]
        if not f.done():
            falhas.append(f"ANA {nome}: sem resposta em 150 s")
            res[k] = []
        elif f.exception():
            falhas.append(f"ANA {nome}: {f.exception()}")
            res[k] = []
        else:
            res[k] = f.result()
    dados["gv"] = res["gv"]
    dados["montante"] = [(p, res[p["cod"]]) for p in C.MONTANTE]
    chuva_h = None
    if leve:
        dados.update({"chuva": None, "glofas": None, "previsao": None})
        try:
            dados["sgb"] = fontes.sgb_ultimo_boletim()
        except Exception as e:
            falhas.append(f"sgb: {type(e).__name__}: {e}")
            dados["sgb"] = "ERRO"
        dados["falhas"] = falhas
        return dados
    from . import previsao
    try:
        chuva_h = previsao.chuva_horaria()
        dados["chuva"] = _chuva_diaria(chuva_h, t)
    except Exception as e:
        falhas.append(f"chuva: {type(e).__name__}: {e}")
        dados["chuva"] = "ERRO"
    for nome, fn in [("glofas", lambda: fontes.glofas(C.GV["lat"], C.GV["lon"])),
                     ("sgb", fontes.sgb_ultimo_boletim)]:
        try:
            dados[nome] = fn()
        except Exception as e:
            falhas.append(f"{nome}: {type(e).__name__}: {e}")
            dados[nome] = "ERRO"
    try:
        if chuva_h is None:
            raise RuntimeError("sem chuva prevista")
        dados["previsao"] = previsao.prever(dados["gv"], dados["montante"], chuva=chuva_h)
    except Exception as e:
        falhas.append(f"previsão: {type(e).__name__}: {e}")
        dados["previsao"] = None
    dados["falhas"] = falhas
    return dados


# ------------------------------------------------------------------ análise

def analisar(d):
    t = agora()
    a = {"t": t}
    u = ultimo_valido(d["gv"])
    a["gv"] = u
    if u:
        a["idade_h"] = (t - u["t"]).total_seconds() / 3600
        h3 = valor_em(d["gv"], u["t"] - dt.timedelta(hours=3))
        h24 = valor_em(d["gv"], u["t"] - dt.timedelta(hours=24))
        a["taxa3"] = (u["nivel_cm"] - h3) / 3 if h3 is not None else None
        a["var24"] = u["nivel_cm"] - h24 if h24 is not None else None
        uq = ultimo_valido(d["gv"], "vazao_m3s")
        a["q_obs"] = uq["vazao_m3s"] if uq else None
    a["faixa"] = faixa(u["nivel_cm"]) if u else None

    mont = []
    for p, s in d["montante"]:
        r = ultimo_valido(s)
        item = {"p": p, "r": r}
        if r:
            h6 = valor_em(s, r["t"] - dt.timedelta(hours=6))
            item["var6"] = r["nivel_cm"] - h6 if h6 is not None else None
            item["idade_h"] = (t - r["t"]).total_seconds() / 3600
            st = "ok"
            if p["inundacao"] and r["nivel_cm"] >= p["inundacao"]:
                st = "inundacao"
            elif p["alerta"] and r["nivel_cm"] >= p["alerta"]:
                st = "alerta"
            item["status"] = st
        mont.append(item)
    a["montante"] = mont

    # Cenário indicativo 5 dias: GloFAS corrigido pelo viés observado hoje
    g = d.get("glofas")
    if isinstance(g, dict) and a.get("q_obs"):
        hoje = t.date().isoformat()
        try:
            i0 = g["time"].index(hoje)
            k = a["q_obs"] / g["river_discharge"][i0] if g["river_discharge"][i0] else 1
            k = min(max(k, 0.5), 2.0)
            cen = []
            for i in range(i0 + 1, min(i0 + 6, len(g["time"]))):
                cen.append({
                    "data": g["time"][i],
                    "central": cota_de_vazao(g["river_discharge"][i] * k),
                    "p75": cota_de_vazao(g["river_discharge_p75"][i] * k) if g.get("river_discharge_p75") else None,
                    "max": cota_de_vazao(g["river_discharge_max"][i] * k),
                })
            a["cenario"], a["glofas_k"] = cen, k
        except (ValueError, KeyError, TypeError):
            pass

    a["previsao"] = d.get("previsao")
    ch = d.get("chuva")
    if isinstance(ch, list) and ch:
        datas = ch[0]["datas"]
        bacia = [p for p in ch if "local" not in p["nome"]]
        a["chuva_bacia"] = [(datas[i], sum((p["mm"][i] or 0) for p in bacia) / len(bacia),
                             max((p["mm"][i] or 0) for p in bacia)) for i in range(len(datas))]
        a["chuva_det"] = ch
    return a


# ------------------------------------------------------------------ mensagens

DIAS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def fmt_d(iso):
    d = dt.date.fromisoformat(iso)
    return f"{DIAS[d.weekday()]} {d:%d/%m}"


def fmt_t(ts):
    return ts.strftime("%d/%m %Hh%M")


def linha_gv(a):
    u = a["gv"]
    if not u:
        return "⚠️ <b>Sem leitura de Valadares</b> nos últimos 3 dias."
    _, em, nome = NIVEIS[a["faixa"]]
    s = f"{em} <b>Rio Doce em Valadares: {u['nivel_cm']:.0f} cm</b> ({nome}) — {fmt_t(u['t'])}"
    tend = []
    if a.get("taxa3") is not None:
        tend.append(f"{a['taxa3']:+.1f} cm/h (3h)")
    if a.get("var24") is not None:
        tend.append(f"{a['var24']:+.0f} cm em 24h")
    if tend:
        s += "\nTendência: " + " · ".join(tend)
    s += "\nReferências SGB: alerta 320 · inundação 360"
    s += "\n" + texto_rua(u["nivel_cm"])
    return s


def bloco_montante(a, so_relevantes=False):
    linhas = []
    for m in a["montante"]:
        p, r = m["p"], m["r"]
        if not r:
            if not so_relevantes:
                linhas.append(f"• {p['nome']}: sem dado")
            continue
        flag = {"ok": "", "alerta": " 🟠 acima do alerta", "inundacao": " 🔴 acima da inundação"}[m["status"]]
        if so_relevantes and not flag and not ((m.get("var6") or 0) >= 30):
            continue
        v = f" ({m['var6']:+.0f} cm/6h)" if m.get("var6") is not None else ""
        velho = " ⏱dado antigo" if m.get("idade_h", 0) > 6 else ""
        linhas.append(f"• {p['nome']}: {r['nivel_cm']:.0f} cm{v}{flag} → chega em GV em ~{p['lag_h']:.0f}h{velho}")
    return "\n".join(linhas)


def bloco_glofas(a):
    cen = a.get("cenario")
    if not cen:
        return ""
    pior = max(c["max"] for c in cen)
    return (f"<i>Referência externa GloFAS (não validada): pico central ~{max(c['central'] for c in cen):.0f} cm, "
            f"pessimista ~{pior:.0f} cm em 5 dias.</i>")


def bloco_cenario(a):
    cen = a.get("cenario")
    if not cen:
        return "Cenário 5 dias: indisponível nesta rodada."
    s = ["<b>Cenário indicativo 5 dias</b> (GloFAS corrigido; <i>experimental, ainda não validado</i>):"]
    for c in cen:
        d = fmt_d(c["data"])
        extra = ""
        if C.RUA_CM and c["max"] >= C.RUA_CM:
            extra = f" → rua: até ~{lamina_rua(c['max']):.0f} cm no pessimista"
        s.append(f"• {d}: ~{c['central']:.0f} cm (pessimista {c['max']:.0f}){extra}")
    return "\n".join(s)


def bloco_previsao(a):
    pv = a.get("previsao")
    if not pv:
        return "<b>Previsão</b>: indisponível nesta rodada (ver fontes com falha)."
    s = [f"<b>Previsão do nível em Valadares</b> (modelo validado; faixa = 80% de chance):"]
    for p in pv["prev"]:
        if p["H"] not in (12, 24, 48, 72, 96, 120):
            continue
        v = p["valido"]
        conf = "" if p["H"] <= 72 else " <i>(baixa confiança)</i>"
        rua = ""
        if C.RUA_CM and p["alto"] >= C.RUA_CM:
            rua = f" → rua: até ~{lamina_rua(p['alto']):.0f} cm" if p["p50"] < C.RUA_CM else \
                  f" → <b>rua: ~{lamina_rua(p['p50']):.0f} cm</b>"
        s.append(f"• +{p['H']}h ({DIAS[v.weekday()]} {v:%d/%m %Hh}): <b>{p['p50']:.0f} cm</b> "
                 f"[{p['baixo']:.0f}–{p['alto']:.0f}]{conf}{rua}")
    return "\n".join(s)


def bloco_chuva(a):
    cb = a.get("chuva_bacia")
    if not cb:
        return ""
    s = ["<b>Chuva prevista na bacia a montante</b> (média · pior sub-bacia):"]
    for data, med, mx in cb[:7]:
        d = fmt_d(data)
        marca = " ⚠️" if mx >= 50 else ""
        s.append(f"• {d}: {med:.0f} mm · {mx:.0f} mm{marca}")
    return "\n".join(s)


def relatorio(a, d):
    partes = [f"<b>🌊 Boletim diário — Rio Doce / Esplanadinha</b>", linha_gv(a), "",
              bloco_previsao(a), "", "<b>Rio acima</b>:", bloco_montante(a), "", bloco_chuva(a), "",
              bloco_glofas(a)]
    sgb = d.get("sgb")
    if sgb == "ERRO":
        partes.append("\nSGB: portal indisponível nesta rodada.")
    elif sgb is None:
        partes.append("\nSGB/SAH Doce: nenhum boletim publicado na operação atual.")
    else:
        partes.append(f"\nSGB/SAH Doce: último boletim — {html.escape(sgb['nome'])}. https://sace.sgb.gov.br/doce")
    if d["falhas"]:
        partes.append("\n<i>Fontes com falha: " + html.escape("; ".join(d["falhas"]))[:500] + "</i>")
    partes.append("\nEmergência: Defesa Civil 199 · alerta SMS: envie seu CEP para 40199.")
    return "\n".join(p for p in partes if p is not None)


def eventos(a, d, st):
    """Decide alertas fora do relatório. Retorna lista de textos e atualiza st."""
    ev = []
    anterior = st.get("faixa")
    f = faixa_com_histerese(a["gv"]["nivel_cm"], anterior) if a["gv"] else None
    if f is not None:
        a["faixa"] = f
        if anterior is not None and f > anterior and f >= 1:
            ev.append(f"⬆️ Nível subiu de faixa: {NIVEIS[anterior][2]} → <b>{NIVEIS[f][2]}</b>")
        elif anterior is not None and f < anterior and anterior >= 2:
            ev.append(f"⬇️ Nível baixou de faixa: {NIVEIS[anterior][2]} → {NIVEIS[f][2]}")
        st["faixa"] = f
    taxa = a.get("taxa3")
    if a["gv"] and taxa is not None and taxa >= C.SUBIDA_RAPIDA_CM_H and a["gv"]["nivel_cm"] >= C.NIVEL_MIN_SUBIDA:
        ult = st.get("subida_rapida_em")
        if not ult or (a["t"] - dt.datetime.fromisoformat(ult)).total_seconds() > 6 * 3600:
            ev.append(f"⚡ <b>Subida rápida</b>: {taxa:+.1f} cm/h nas últimas 3h.")
            st["subida_rapida_em"] = a["t"].isoformat()
    # postos a montante cruzando cotas SGB
    sm = st.setdefault("montante", {})
    for m in a["montante"]:
        if not m["r"]:
            continue
        cod, s = m["p"]["cod"], m.get("status", "ok")
        rank = {"ok": 0, "alerta": 1, "inundacao": 2}
        prev = sm.get(cod, "ok")
        if rank[s] < rank[prev]:
            lim = m["p"]["inundacao"] if prev == "inundacao" else m["p"]["alerta"]
            if m["r"]["nivel_cm"] >= lim - 20:  # histerese de 20 cm a montante
                s = prev
        if rank[s] > rank[prev]:
            ev.append(f"🌊 {m['p']['nome']} passou da cota de {'inundação' if s == 'inundacao' else 'alerta'} "
                      f"({m['r']['nivel_cm']:.0f} cm). Onda chega em Valadares em ~{m['p']['lag_h']:.0f}h.")
        sm[cod] = s
    # dado parado
    velho = (a.get("idade_h") or 99) > C.DADO_VELHO_H
    if velho and not st.get("aviso_dado_velho"):
        ana_fora = not a["gv"] and all(m["r"] is None for m in a["montante"])
        if ana_fora:
            ev.append("⚠️ <b>O serviço de telemetria da ANA está fora do ar</b> (nenhum posto responde). Sem dados, o "
                      "monitor não consegue avisar. Enquanto isso: Defesa Civil (SMS 40199) e portal do SGB "
                      "(sace.sgb.gov.br/doce). Aviso de novo quando voltar.")
        else:
            ev.append("⚠️ A telemetria de Valadares parou de atualizar (> 3h). Acompanhe pelo portal do SGB e a Defesa Civil.")
    if not velho and st.get("aviso_dado_velho"):
        ev.append("✅ Telemetria de Valadares voltou a atualizar.")
    st["aviso_dado_velho"] = velho
    # boletim novo do SGB
    sgb = d.get("sgb")
    if isinstance(sgb, dict) and sgb["id"] != st.get("sgb_id"):
        ev.append(f"📄 Novo boletim do SGB/SAH Doce: {html.escape(sgb['nome'])}\nhttps://sace.sgb.gov.br/doce")
        st["sgb_id"] = sgb["id"]
    # previsão do modelo para a rua (só até 72h) — máquina de estados para evitar alerta repetido:
    # nenhum → possível → provável; só avisa quando PIORA (sobe de estado, pico +15 cm, ou chegada < 24h)
    # e uma vez quando o risco passa.
    pv = a.get("previsao")
    curto = [p for p in pv["prev"] if p["H"] <= 72] if pv else []
    if curto and C.RUA_CM:
        prov = [p for p in curto if p["p50"] >= C.RUA_CM]
        poss = [p for p in curto if p["alto"] >= C.RUA_CM]
        pico = max(curto, key=lambda x: x["p50"])
        r = st.get("rua", {"estado": 0, "pico": 0, "iminente": False})
        estado = 2 if prov else 1 if poss else 0
        iminente = bool(prov) and prov[0]["H"] <= 24
        if estado > 0 or pico["alto"] >= C.RUA_CM - 15:
            r.pop("baixo_desde", None)
        if estado > r["estado"] or (estado == 2 and (pico["p50"] >= r["pico"] + 15 or (iminente and not r["iminente"]))):
            if estado == 2:
                p = prov[0]
                ev.append(f"🚨 <b>ÁGUA PROVÁVEL NA SUA RUA</b> a partir de ~{fmt_t(p['valido'])} (+{p['H']}h). "
                          f"Pico previsto ~{pico['p50']:.0f} cm [{pico['baixo']:.0f}–{pico['alto']:.0f}] "
                          f"→ ~{lamina_rua(pico['p50']):.0f} cm de água na rua (até ~{lamina_rua(pico['alto']):.0f}).")
            else:
                p = poss[0]
                ev.append(f"⚠️ <b>Possível água na sua rua</b> nos próximos 3 dias: o cenário pessimista passa de "
                          f"{C.RUA_CM} cm a partir de ~{fmt_t(p['valido'])} (previsão central {pico['p50']:.0f} cm). "
                          "Fique atento aos próximos avisos.")
            r = {"estado": estado, "pico": pico["p50"], "iminente": iminente}
        elif estado == 0 and r["estado"] > 0 and pico["alto"] < C.RUA_CM - 15:
            # só libera depois de 24h SEGUIDAS com risco baixo (a previsão de chuva oscila entre rodadas)
            desde = r.get("baixo_desde") or a["t"].isoformat()
            r["baixo_desde"] = desde
            if (a["t"] - dt.datetime.fromisoformat(desde)).total_seconds() >= 24 * 3600:
                ev.append(f"✅ Risco de água na sua rua diminuiu: há 24h a previsão máxima para 72h fica abaixo de "
                          f"{C.RUA_CM - 15} cm (agora ~{pico['p50']:.0f}, pessimista {pico['alto']:.0f}).")
                r = {"estado": 0, "pico": 0, "iminente": False}
        st["rua"] = r  # se o risco recua sem zerar, mantém o estado (não re-alerta na oscilação)
    return ev


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--relatorio", action="store_true", help="força o relatório completo")
    ap.add_argument("--leve", action="store_true", help="rodada leve: sem previsão/chuva (só biblioteca padrão)")
    ap.add_argument("--teste-alerta", action="store_true", help="envia um alerta de teste e sai")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if args.teste_alerta:
        enviar_telegram("🚨 <b>TESTE DE ALERTA — Rio Doce</b>\nSe este aviso tocou com o celular no silencioso/"
                        "não perturbe, a configuração está certa. Nenhuma ação necessária.", args.dry_run)
        return 0
    st = carregar_estado()
    primeira_vez = not st
    try:
        d = coletar(leve=args.leve)
        a = analisar(d)
        # registros (independem de o Telegram funcionar)
        if not args.dry_run:
            anexar_log(d["gv"], st.get("ultimo_log"))
            if a["gv"]:
                st["ultimo_log"] = max(r["t"] for r in d["gv"] if r["nivel_cm"] is not None).isoformat()
            if not args.leve:
                st["previsao_falhas"] = 0 if d.get("previsao") else st.get("previsao_falhas", 0) + 1
                pv = d.get("previsao")
                if not (pv is not None and pv["emitida"].isoformat() == st.get("ultima_previsao")):
                    registrar_previsao(pv, d["falhas"])
                    if pv:
                        st["ultima_previsao"] = pv["emitida"].isoformat()
        # alertas: calculados numa CÓPIA do estado; só vira definitivo se o envio der certo
        st_novo = copy.deepcopy(st)
        evs = eventos(a, d, st_novo)
        hoje = a["t"].date().isoformat()
        mandar_rel = not args.leve and (args.relatorio or primeira_vez or (
            a["t"].hour >= C.HORA_RELATORIO and st.get("relatorio_dia") != hoje))
        msgs = []
        if mandar_rel:
            msgs.append(relatorio(a, d))
            st_novo["relatorio_dia"] = hoje
            if evs:
                msgs.append("<b>Destaques:</b>\n" + "\n".join(evs))
        elif evs:
            msgs.append("<b>🚨 Rio Doce — atualização</b>\n" + linha_gv(a) + "\n\n" + "\n\n".join(evs)
                        + ("\n\n" + bloco_montante(a, so_relevantes=True) if any("🌊" in e for e in evs) else ""))
        try:
            for m in msgs:
                enviar_telegram(m, args.dry_run)
        except Exception as e:
            # NÃO grava st_novo: na próxima rodada os mesmos alertas serão recalculados e reenviados
            st["falha_envio"] = st.get("falha_envio", 0) + 1
            st["ultima_execucao"] = a["t"].isoformat()
            print(f"Falha ao enviar pelo Telegram ({st['falha_envio']}x): {e}", file=sys.stderr)
            if not args.dry_run:
                salvar_estado(st)
            return 2
        st = st_novo
        st.pop("falha_envio", None)
        if not msgs:
            print(f"[{a['t']:%d/%m %H:%M}] sem novidades — {linha_gv(a).splitlines()[0]}")
        st["ultima_execucao"] = a["t"].isoformat()
        if not args.leve:
            st["ultima_completa"] = a["t"].isoformat()
        st.pop("falha_consecutiva", None)
    except Exception:
        tb = traceback.format_exc()
        print(tb, file=sys.stderr)
        n = st.get("falha_consecutiva", 0) + 1
        st["falha_consecutiva"] = n
        if n in (2, 6, 24):
            try:
                enviar_telegram(f"⚠️ Monitor do Rio Doce falhou {n}x seguidas. Último erro:\n<code>"
                                f"{html.escape(tb[-600:])}</code>", args.dry_run)
            except Exception:
                pass
        if not args.dry_run:
            salvar_estado(st)
        return 1
    if not args.dry_run:
        salvar_estado(st)
    return 0


if __name__ == "__main__":
    sys.exit(main())
