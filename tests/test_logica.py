import datetime as dt
import unittest

from monitor import run


class TestLogica(unittest.TestCase):
    def test_curva_reproduz_picos(self):
        self.assertAlmostEqual(run.cota_de_vazao(5489.3), 606, delta=5)
        self.assertAlmostEqual(run.cota_de_vazao(4060.8), 513, delta=10)  # curva-chave muda entre anos
        self.assertAlmostEqual(run.cota_de_vazao(973.27), 255, delta=5)

    def test_faixas(self):
        self.assertEqual(run.faixa(200), 0)
        self.assertEqual(run.faixa(255), 1)
        self.assertEqual(run.faixa(320), 2)
        self.assertEqual(run.faixa(339), 2)
        self.assertEqual(run.faixa(345), 4)   # rua calibrada em 341 cm vem antes da inundação oficial

    def test_histerese(self):
        self.assertEqual(run.faixa_com_histerese(315, 2), 2)   # 5 cm abaixo: segura
        self.assertEqual(run.faixa_com_histerese(309, 2), 1)   # 11 cm abaixo: desce
        self.assertEqual(run.faixa_com_histerese(330, 1), 2)   # sobe na hora

    def test_lamina_rua_bate_observacoes(self):
        self.assertLess(run.lamina_rua(367), 15)          # 2026: abaixo do meio-fio
        self.assertGreater(run.lamina_rua(376), 15)       # 2025: acima do meio-fio
        self.assertAlmostEqual(run.lamina_rua(606), 130, delta=10)  # 2022: ~1,3 m

    def test_subida_rapida(self):
        t0 = dt.datetime(2026, 1, 1, 12)
        serie = [{"t": t0 - dt.timedelta(hours=3), "nivel_cm": 300, "vazao_m3s": None, "chuva_mm": None},
                 {"t": t0, "nivel_cm": 318, "vazao_m3s": None, "chuva_mm": None}]
        run.agora = lambda: t0
        a = run.analisar({"gv": serie, "montante": [], "glofas": None, "chuva": None})
        evs = run.eventos(a, {"sgb": None}, {})
        self.assertTrue(any("Subida rápida" in e for e in evs))


class TestEntrega(unittest.TestCase):
    def test_falha_do_telegram_nao_perde_alerta(self):
        import json, os, tempfile
        from monitor import config as C
        tmp = tempfile.mkdtemp()
        C.STATE_PATH, C.LOG_CSV = os.path.join(tmp, "state.json"), os.path.join(tmp, "log.csv")
        json.dump({"faixa": 1, "relatorio_dia": "2026-01-20"}, open(C.STATE_PATH, "w"))
        t0 = dt.datetime(2026, 1, 20, 12)
        run.agora = lambda: t0
        serie = [{"t": t0 - dt.timedelta(hours=h), "nivel_cm": 330.0 - h, "vazao_m3s": 2000.0, "chuva_mm": None}
                 for h in reversed(range(0, 30))]
        run.coletar = lambda leve=False: {"gv": serie, "montante": [], "chuva": None, "glofas": None,
                                          "sgb": None, "previsao": None, "falhas": []}
        enviados = []
        def falha(m, dry):
            raise RuntimeError("Telegram fora do ar")
        run.enviar_telegram = falha
        self.assertEqual(run.main(["--leve"]), 2)
        self.assertEqual(json.loads(open(C.STATE_PATH).read())["faixa"], 1)     # alerta NÃO marcado como enviado
        run.enviar_telegram = lambda m, dry: enviados.append(m)
        self.assertEqual(run.main(["--leve"]), 0)
        self.assertTrue(any("ALERTA" in m for m in enviados))           # reenviado na rodada seguinte
        self.assertEqual(json.loads(open(C.STATE_PATH).read())["faixa"], 2)


class TestPrevisao(unittest.TestCase):
    def test_modelo_carrega_e_preve(self):
        import pandas as pd
        from monitor import previsao
        t0 = dt.datetime(2026, 1, 20, 12)
        gv = [{"t": t0 - dt.timedelta(minutes=15 * i), "nivel_cm": 250.0, "vazao_m3s": 1000.0, "chuva_mm": None}
              for i in range(0, 4 * 72)]
        idx = pd.date_range(t0 - dt.timedelta(hours=72), t0 + dt.timedelta(hours=144), freq="1h")
        chuva = pd.DataFrame({f"r_{k}": 0.0 for k in ["piranga", "piracicaba", "santoantonio", "docemedio", "gv"]},
                             index=idx)
        r = previsao.prever(gv, [], chuva=chuva)
        self.assertEqual(len(r["prev"]), 8)
        for p in r["prev"]:
            self.assertLessEqual(p["baixo"], p["p50"])
            self.assertLessEqual(p["p50"], p["alto"])
            self.assertLess(abs(p["p50"] - 250), 60)   # sem chuva e rio estável: não inventa cheia


if __name__ == "__main__":
    unittest.main()
