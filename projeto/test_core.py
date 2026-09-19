"""test_core.py — testes unitários de core.py (unittest, sem dependências externas)."""
from __future__ import annotations

import math
import tempfile
import unittest
from pathlib import Path

import core

MODELO = "modelo-teste"


def _vetor(dominante: int, dim: int = 4, ruido: float = 0.0) -> list:
    v = [0.0] * dim
    v[dominante] = 1.0
    if ruido:
        v[(dominante + 1) % dim] += ruido
    return v


class TestAutorizacao(unittest.TestCase):
    def test_nivel1_somente_geral(self):
        u = core.User(id="a", name="A", level=1, division="")
        self.assertTrue(core.is_authorized(u, "geral"))
        self.assertFalse(core.is_authorized(u, "toxinas"))
        self.assertFalse(core.is_authorized(u, "ministerial"))

    def test_nivel2_restrito_a_propria_divisao(self):
        diretor_toxinas = core.User(id="d1", name="D1", level=2, division="Toxinas")
        self.assertTrue(core.is_authorized(diretor_toxinas, "geral"))
        self.assertTrue(core.is_authorized(diretor_toxinas, "toxinas"))
        self.assertFalse(core.is_authorized(diretor_toxinas, "fiscalizacao"))
        self.assertFalse(core.is_authorized(diretor_toxinas, "ministerial"))

    def test_nivel3_acessa_tudo(self):
        ministro = core.User(id="m1", name="M1", level=3, division="")
        for area in core.AREAS:
            self.assertTrue(core.is_authorized(ministro, area))

    def test_desconhecido_nunca_autorizado(self):
        self.assertFalse(core.is_authorized(None, "geral"))

    def test_area_invalida_levanta_erro(self):
        u = core.User(id="a", name="A", level=1, division="")
        with self.assertRaises(core.ErroDominio):
            core.is_authorized(u, "area-que-nao-existe")


class TestStoreCadastro(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.caminho_banco = Path(self._tmp.name) / "cofre.sqlite3"
        self.store = core.Store(self.caminho_banco)

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def test_cadastro_minimo_de_tres_embeddings(self):
        with self.assertRaises(core.ErroDominio):
            self.store.enroll(
                user_id="x", name="X", level=1, division="", consentimento=True,
                model_id=MODELO, embeddings=[_vetor(0), _vetor(0, ruido=0.01)],
            )

    def test_cadastro_sem_consentimento_falha(self):
        with self.assertRaises(core.ErroDominio):
            self.store.enroll(
                user_id="x", name="X", level=1, division="", consentimento=False,
                model_id=MODELO,
                embeddings=[_vetor(0), _vetor(0, ruido=0.01), _vetor(0, ruido=-0.01)],
            )

    def test_id_reservado_desconhecido_rejeitado(self):
        with self.assertRaises(core.ErroDominio):
            self.store.enroll(
                user_id=core.ID_DESCONHECIDO, name="X", level=1, division="",
                consentimento=True, model_id=MODELO,
                embeddings=[_vetor(0), _vetor(0, ruido=0.01), _vetor(0, ruido=-0.01)],
            )

    def test_nivel2_exige_divisao_valida(self):
        with self.assertRaises(core.ErroDominio):
            self.store.enroll(
                user_id="d1", name="D1", level=2, division="", consentimento=True,
                model_id=MODELO,
                embeddings=[_vetor(1), _vetor(1, ruido=0.01), _vetor(1, ruido=-0.01)],
            )

    def test_embedding_com_norma_zero_rejeitado(self):
        with self.assertRaises(core.ErroDominio):
            self.store.enroll(
                user_id="x", name="X", level=1, division="", consentimento=True,
                model_id=MODELO,
                embeddings=[[0.0, 0.0, 0.0, 0.0], _vetor(0), _vetor(0, ruido=0.01)],
            )

    def test_embedding_nao_finito_rejeitado(self):
        with self.assertRaises(core.ErroDominio):
            self.store.enroll(
                user_id="x", name="X", level=1, division="", consentimento=True,
                model_id=MODELO,
                embeddings=[[math.nan, 0.0, 0.0, 0.0], _vetor(0), _vetor(0, ruido=0.01)],
            )

    def test_numero_muito_grande_trata_como_invalido(self):
        with self.assertRaises(core.ErroDominio):
            self.store.enroll(
                user_id="x", name="X", level=1, division="", consentimento=True,
                model_id=MODELO,
                embeddings=[
                    [float("1" + "0" * 400), 0.0, 0.0, 0.0],
                    _vetor(0), _vetor(0, ruido=0.01),
                ],
            )

    def test_id_duplicado_nao_sobrescreve(self):
        embeddings = [_vetor(0), _vetor(0, ruido=0.01), _vetor(0, ruido=-0.01)]
        self.store.enroll(
            user_id="x", name="Original", level=1, division="", consentimento=True,
            model_id=MODELO, embeddings=embeddings,
        )
        with self.assertRaises(core.ErroDominio):
            self.store.enroll(
                user_id="x", name="Outro Nome", level=1, division="", consentimento=True,
                model_id=MODELO, embeddings=embeddings,
            )
        usuario = self.store.get_user("x")
        self.assertEqual(usuario.name, "Original")

    def test_apenas_um_ministro_por_banco(self):
        embeddings_a = [_vetor(2), _vetor(2, ruido=0.01), _vetor(2, ruido=-0.01)]
        embeddings_b = [_vetor(3), _vetor(3, ruido=0.01), _vetor(3, ruido=-0.01)]
        self.store.enroll(
            user_id="m1", name="Ministro 1", level=3, division="", consentimento=True,
            model_id=MODELO, embeddings=embeddings_a,
        )
        with self.assertRaises(core.ErroDominio):
            self.store.enroll(
                user_id="m2", name="Ministro 2", level=3, division="", consentimento=True,
                model_id=MODELO, embeddings=embeddings_b,
            )


class TestAccessService(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = core.Store(Path(self._tmp.name) / "cofre.sqlite3")
        self.store.enroll(
            user_id="basico", name="Básico", level=1, division="", consentimento=True,
            model_id=MODELO,
            embeddings=[_vetor(0), _vetor(0, ruido=0.02), _vetor(0, ruido=-0.02)],
        )
        self.store.enroll(
            user_id="diretor", name="Diretor", level=2, division="Toxinas", consentimento=True,
            model_id=MODELO,
            embeddings=[_vetor(1), _vetor(1, ruido=0.02), _vetor(1, ruido=-0.02)],
        )
        self.servico = core.AccessService(self.store, MODELO, threshold=0.8, margin=0.1)

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def test_identifica_usuario_proximo(self):
        usuario, distancia, motivo = self.servico.identify(_vetor(0))
        self.assertEqual(usuario.id, "basico")
        self.assertEqual(motivo, "identificado")

    def test_vetor_distante_e_desconhecido(self):
        usuario, distancia, motivo = self.servico.identify([0.0, 0.0, 0.0, 1.0])
        self.assertIsNone(usuario)
        self.assertEqual(motivo, core.RAZAO_DESCONHECIDO)

    def test_attempt_autoriza_area_compativel(self):
        decisao = self.servico.attempt(_vetor(1), "toxinas", source="simulacao", simulated=True)
        self.assertTrue(decisao.granted)
        self.assertEqual(decisao.user_id, "diretor")

    def test_attempt_nega_area_incompativel(self):
        decisao = self.servico.attempt(_vetor(1), "fiscalizacao", source="simulacao", simulated=True)
        self.assertFalse(decisao.granted)

    def test_falha_informada_nega_mesmo_com_embedding(self):
        decisao = self.servico.attempt(
            _vetor(0), "geral", source="simulacao",
            failure=core.RAZAO_MULTIPLOS_ROSTOS, simulated=True,
        )
        self.assertFalse(decisao.granted)
        self.assertEqual(decisao.reason, core.RAZAO_MULTIPLOS_ROSTOS)

    def test_fonte_simulacao_forca_simulated_1(self):
        self.servico.attempt(_vetor(0), "geral", source="simulacao", simulated=False)
        tentativas = self.store.attempts()
        self.assertEqual(tentativas[-1]["simulated"], 1)

    def test_limiar_fora_do_intervalo_rejeitado(self):
        with self.assertRaises(core.ErroDominio):
            core.AccessService(self.store, MODELO, threshold=0.0, margin=0.1)
        with self.assertRaises(core.ErroDominio):
            core.AccessService(self.store, MODELO, threshold=2.0, margin=0.1)


class TestExportacao(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.caminho_banco = Path(self._tmp.name) / "cofre.sqlite3"
        self.store = core.Store(self.caminho_banco)

    def tearDown(self):
        self.store.close()
        self._tmp.cleanup()

    def test_nao_exporta_sobre_o_proprio_banco(self):
        with self.assertRaises(core.ErroDominio):
            self.store.export(self.caminho_banco)

    def test_exporta_com_bom_utf8(self):
        decisao = core.Decision(
            user_id=None, user_name=core.ID_DESCONHECIDO, user_level=None,
            area="geral", granted=False, reason="desconhecido", distance=None,
        )
        self.store.log(decisao, source="simulacao", simulated=True)
        destino = Path(self._tmp.name) / "saida.csv"
        self.store.export(destino)
        conteudo_bruto = destino.read_bytes()
        self.assertTrue(conteudo_bruto.startswith(b"\xef\xbb\xbf"))

    def test_neutraliza_valor_com_prefixo_de_formula(self):
        decisao = core.Decision(
            user_id=None, user_name="=CMD('calc')", user_level=None,
            area="geral", granted=False, reason="desconhecido", distance=None,
        )
        self.store.log(decisao, source="simulacao", simulated=True)
        destino = Path(self._tmp.name) / "saida2.csv"
        self.store.export(destino)
        conteudo = destino.read_text(encoding="utf-8-sig")
        self.assertIn("'=CMD", conteudo)


if __name__ == "__main__":
    unittest.main()
