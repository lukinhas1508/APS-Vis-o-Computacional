"""test_liveness.py — testes da prova de vida (liveness.py), sem câmera.

A máquina de estados é Python puro: os testes simulam sequências de quadros
de uma pessoa real e de uma foto (parada ou balançada na mão).
"""
from __future__ import annotations

import random
import unittest

import liveness as lv

DT = 0.08  # ~12 quadros por segundo

FRENTE = lv.FaceMetrics(faces=1, yaw=0.5, ear=0.30, mar=0.03, center=(0.5, 0.5), size=0.35)


def pose(**kw) -> lv.FaceMetrics:
    base = dict(faces=1, yaw=0.5, ear=0.30, mar=0.03, center=(0.5, 0.5), size=0.35)
    base.update(kw)
    return lv.FaceMetrics(**base)


ACAO = {
    "blink": pose(ear=0.10),
    "left": pose(yaw=0.75),
    "right": pose(yaw=0.25),
    "mouth": pose(mar=0.6),
}


def rodar(sessao, quadros, t0=0.0):
    t = t0
    for q in quadros:
        t += DT
        sessao.step(q, t)
    return t


def quadros_pessoa_real(seq):
    q = [FRENTE] * 3
    for ch in seq:
        q += [ACAO[ch], ACAO[ch], FRENTE, FRENTE]
    return q


def nova_sessao(seed: int) -> lv.LivenessSession:
    return lv.LivenessSession(now=0.0, rand=random.Random(seed).random)


class TestLiveness(unittest.TestCase):
    def test_pessoa_real_e_aprovada(self):
        s = nova_sessao(1)
        t = rodar(s, quadros_pessoa_real(s.seq))
        self.assertEqual(s.status, "aprovado")
        self.assertTrue(s.vivo_e_presente(t))

    def test_sequencia_tem_piscar_e_tres_desafios_distintos(self):
        for seed in range(50):
            seq = lv.new_sequence(random.Random(seed).random)
            self.assertEqual(len(seq), 3)
            self.assertIn("blink", seq)
            self.assertEqual(len(set(seq)), 3)

    def test_foto_parada_nunca_e_aprovada(self):
        s = nova_sessao(2)
        t = 0.0
        for _ in range(400):  # ~32 s
            t += DT
            s.step(FRENTE, t)
            self.assertFalse(s.vivo_e_presente(t))

    def test_foto_balancada_no_celular_nunca_e_aprovada(self):
        rng = random.Random(3)
        s = nova_sessao(3)
        t = 0.0
        for i in range(500):
            t += DT
            q = pose(
                yaw=0.5 + (rng.random() - 0.5) * 0.08,  # inclinar um plano não cria paralaxe
                ear=0.28 + rng.random() * 0.04,          # olhos da foto não fecham
                mar=0.02 + rng.random() * 0.05,          # boca da foto não abre
                center=(0.5 + 0.08 * ((i % 20) / 20 - 0.5), 0.5),
                size=0.3 + 0.05 * rng.random(),
            )
            s.step(q, t)
            self.assertFalse(s.vivo_e_presente(t))

    def test_virar_para_o_lado_errado_reprova(self):
        for seed in range(30):
            s = nova_sessao(seed)
            giros = [i for i, c in enumerate(s.seq) if c in ("left", "right")]
            if not giros:
                continue
            k = giros[0]
            quadros = [FRENTE, FRENTE]
            for ch in s.seq[:k]:
                quadros += [ACAO[ch], FRENTE]
            quadros.append(ACAO["right" if s.seq[k] == "left" else "left"])
            rodar(s, quadros)
            self.assertEqual(s.status, "reprovado")
            self.assertEqual(s.reason, "desafio_incorreto")
            return
        self.fail("nenhuma sequência com giro encontrada")

    def test_tempo_esgotado_reprova(self):
        s = nova_sessao(5)
        rodar(s, [FRENTE] * int(lv.STEP_TIMEOUT_S / DT + 5))
        self.assertEqual(s.status, "reprovado")
        self.assertEqual(s.reason, "tempo_esgotado")

    def test_rosto_sai_do_quadro_invalida_aprovacao(self):
        s = nova_sessao(6)
        t = rodar(s, quadros_pessoa_real(s.seq))
        id_aprovado = s.id
        t = rodar(s, [lv.FaceMetrics(faces=0)] * 15, t)
        rodar(s, [FRENTE], t)
        self.assertNotEqual(s.status, "aprovado")
        self.assertNotEqual(s.id, id_aprovado)

    def test_troca_brusca_de_rosto_recomeça(self):
        s = nova_sessao(7)
        t = rodar(s, quadros_pessoa_real(s.seq))
        rodar(s, [pose(center=(0.85, 0.5))], t)
        self.assertEqual(s.reason, "rosto_trocado")
        self.assertNotEqual(s.status, "aprovado")

    def test_dois_rostos_recomeça(self):
        s = nova_sessao(8)
        t = rodar(s, quadros_pessoa_real(s.seq))
        rodar(s, [lv.FaceMetrics(faces=2)], t)
        self.assertEqual(s.reason, "multiplos_rostos")
        self.assertNotEqual(s.status, "aprovado")

    def test_aprovacao_expira(self):
        s = nova_sessao(9)
        t = rodar(s, quadros_pessoa_real(s.seq))
        t = rodar(s, [FRENTE] * int(lv.SESSION_TTL_S / DT + 5), t)
        self.assertFalse(s.vivo_e_presente(t))

    def test_metricas_de_landmarks(self):
        pts = [(0.5, 0.5)] * 468
        pts = list(pts)
        pts[33], pts[263], pts[1] = (0.4, 0.45), (0.6, 0.45), (0.55, 0.55)
        # olho direito: 33,160,158,133,153,144 ; olho esquerdo: 263,387,385,362,380,373
        pts[133], pts[160], pts[158], pts[153], pts[144] = (0.48, 0.45), (0.43, 0.44), (0.45, 0.44), (0.45, 0.46), (0.43, 0.46)
        pts[362], pts[387], pts[385], pts[380], pts[373] = (0.52, 0.45), (0.57, 0.44), (0.55, 0.44), (0.55, 0.46), (0.57, 0.46)
        pts[13], pts[14], pts[78], pts[308] = (0.5, 0.60), (0.5, 0.62), (0.45, 0.61), (0.55, 0.61)
        pts[10], pts[152] = (0.5, 0.2), (0.5, 0.8)
        m = lv.metrics_from_landmarks([pts])
        self.assertEqual(m.faces, 1)
        self.assertAlmostEqual(m.yaw, 0.75)
        self.assertAlmostEqual(m.ear, 0.25)
        self.assertAlmostEqual(m.mar, 0.2)
        self.assertEqual(lv.metrics_from_landmarks([pts, pts]).faces, 2)
        self.assertEqual(lv.metrics_from_landmarks([]).faces, 0)

    def test_giro_imune_a_girar_a_foto_no_plano(self):
        """Girar o celular (roll) não pode ser confundido com virar a cabeça."""
        import math

        base = {33: (-0.1, 0.0), 263: (0.1, 0.0), 1: (0.0, 0.08)}
        for graus in (-40, -20, 0, 20, 40):
            a = math.radians(graus)
            pts = [(0.5, 0.5)] * 468
            for i, (x, y) in base.items():
                pts[i] = (0.5 + x * math.cos(a) - y * math.sin(a), 0.5 + x * math.sin(a) + y * math.cos(a))
            m = lv.metrics_from_landmarks([pts])
            self.assertAlmostEqual(m.yaw, 0.5, places=6, msg=f"roll {graus}°")


if __name__ == "__main__":
    unittest.main()
