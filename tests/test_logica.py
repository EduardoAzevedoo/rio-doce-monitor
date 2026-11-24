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


if __name__ == "__main__":
    unittest.main()
