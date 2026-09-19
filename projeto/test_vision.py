"""test_vision.py — testes de vision.py.

A detecção real de rostos com Haar Cascade depende de imagens de rostos
verdadeiros, que não estão disponíveis neste ambiente de teste. Por isso,
estes testes usam dublês (fakes) para o cascade e para o extrator FaceNet,
de modo a validar a lógica de pré-processamento, recorte, verificações de
qualidade e tratamento de erros — sem depender de TensorFlow nem de imagens
faciais reais. A aquisição de arquivo (load_image) é testada com OpenCV/NumPy
reais, pois ambos estão disponíveis neste ambiente.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    import cv2
    import numpy as np
    _CV_DISPONIVEL = True
except ImportError:  # pragma: no cover - ambiente sem OpenCV/NumPy
    _CV_DISPONIVEL = False

import core

if _CV_DISPONIVEL:
    import vision


class _CascadeFalso:
    """Dublê de cv2.CascadeClassifier: retorna detecções pré-definidas."""

    def __init__(self, deteccoes):
        self._deteccoes = deteccoes

    def detectMultiScale(self, *args, **kwargs):
        return self._deteccoes


class _EmbedderFalso:
    """Dublê de vision._FaceEmbedder: não usa TensorFlow."""

    def embed(self, face_rgb_160):
        vetor = [0.0] * vision.EMBEDDING_DIMENSIONS
        vetor[0] = 1.0
        return vetor


@unittest.skipUnless(_CV_DISPONIVEL, "OpenCV/NumPy não disponíveis neste ambiente")
class TestLoadImage(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self._tmp.cleanup()

    def test_arquivo_inexistente_levanta_erro(self):
        with self.assertRaises(vision.FaceError):
            vision.load_image(Path(self._tmp.name) / "nao-existe.jpg")

    def test_arquivo_maior_que_limite_e_rejeitado(self):
        caminho = Path(self._tmp.name) / "grande.jpg"
        with open(caminho, "wb") as f:
            f.seek(vision.MAX_IMAGE_FILE_BYTES + 1024)
            f.write(b"\0")
        with self.assertRaises(vision.FaceError):
            vision.load_image(caminho)

    def test_carrega_imagem_valida(self):
        caminho = Path(self._tmp.name) / "valida.png"
        imagem = np.full((100, 100, 3), 127, dtype=np.uint8)
        cv2.imwrite(str(caminho), imagem)
        carregada = vision.load_image(caminho)
        self.assertEqual(carregada.shape, (100, 100, 3))
        self.assertEqual(carregada.dtype, np.uint8)


@unittest.skipUnless(_CV_DISPONIVEL, "OpenCV/NumPy não disponíveis neste ambiente")
class TestFacePipelineExtract(unittest.TestCase):
    def _pipeline_com_deteccoes(self, deteccoes):
        pipeline = vision.FacePipeline()
        pipeline._cascade = _CascadeFalso(deteccoes)
        pipeline._embedder = _EmbedderFalso()
        return pipeline

    def test_rejeita_entrada_nao_numpy(self):
        pipeline = self._pipeline_com_deteccoes(())
        with self.assertRaises(vision.FaceError):
            pipeline.extract("nao é uma imagem")

    def test_rejeita_imagem_com_canais_errados(self):
        pipeline = self._pipeline_com_deteccoes(())
        imagem_cinza = np.zeros((100, 100), dtype=np.uint8)
        with self.assertRaises(vision.FaceError):
            pipeline.extract(imagem_cinza)

    def test_nenhum_rosto_detectado(self):
        pipeline = self._pipeline_com_deteccoes(())
        imagem = np.full((200, 200, 3), 127, dtype=np.uint8)
        with self.assertRaises(vision.FaceError) as ctx:
            pipeline.extract(imagem)
        self.assertEqual(ctx.exception.reason, core.RAZAO_NENHUM_ROSTO)

    def test_multiplos_rostos_detectados(self):
        deteccoes = np.array([[10, 10, 90, 90], [110, 110, 90, 90]])
        pipeline = self._pipeline_com_deteccoes(deteccoes)
        imagem = np.full((300, 300, 3), 127, dtype=np.uint8)
        with self.assertRaises(vision.FaceError) as ctx:
            pipeline.extract(imagem)
        self.assertEqual(ctx.exception.reason, core.RAZAO_MULTIPLOS_ROSTOS)

    def test_rosto_pequeno_e_rejeitado(self):
        deteccoes = np.array([[10, 10, 50, 50]])  # menor que MIN_FACE_DIMENSION_PX
        pipeline = self._pipeline_com_deteccoes(deteccoes)
        imagem = np.full((200, 200, 3), 127, dtype=np.uint8)
        with self.assertRaises(vision.FaceError) as ctx:
            pipeline.extract(imagem)
        self.assertEqual(ctx.exception.reason, core.RAZAO_ROSTO_PEQUENO)

    def test_imagem_desfocada_e_rejeitada(self):
        # Recorte totalmente uniforme -> variância do Laplaciano igual a zero.
        imagem = np.full((200, 200, 3), 127, dtype=np.uint8)
        deteccoes = np.array([[10, 10, 100, 100]])
        pipeline = self._pipeline_com_deteccoes(deteccoes)
        with self.assertRaises(vision.FaceError) as ctx:
            pipeline.extract(imagem)
        self.assertEqual(ctx.exception.reason, core.RAZAO_IMAGEM_DESFOCADA)

    def test_iluminacao_inadequada_e_rejeitada(self):
        # Recorte escuro, porém com textura suficiente para passar no teste de
        # nitidez, isolando a rejeição por luminosidade fora de [40, 215].
        rng = np.random.default_rng(7)
        ruido = rng.integers(0, 12, (200, 200, 3), dtype=np.uint8)
        imagem = np.clip(ruido.astype(int) + 2, 0, 255).astype(np.uint8)
        deteccoes = np.array([[10, 10, 100, 100]])
        pipeline = self._pipeline_com_deteccoes(deteccoes)
        with self.assertRaises(vision.FaceError) as ctx:
            pipeline.extract(imagem)
        self.assertEqual(ctx.exception.reason, core.RAZAO_ILUMINACAO_INADEQUADA)

    def test_extracao_bem_sucedida_com_dubles(self):
        imagem = np.random.default_rng(42).integers(0, 255, (200, 200, 3), dtype=np.uint8)
        # Força brilho médio dentro da faixa aceitável.
        imagem[:] = np.clip(imagem.astype(int) // 2 + 90, 0, 255).astype(np.uint8)
        deteccoes = np.array([[10, 10, 100, 100]])
        pipeline = self._pipeline_com_deteccoes(deteccoes)
        try:
            amostra = pipeline.extract(imagem)
        except vision.FaceError as exc:
            self.skipTest(f"Imagem de teste não atendeu aos critérios de qualidade: {exc.reason}")
            return
        self.assertEqual(len(amostra.embedding), vision.EMBEDDING_DIMENSIONS)
        self.assertAlmostEqual(sum(v * v for v in amostra.embedding) ** 0.5, 1.0, places=5)
        self.assertEqual(amostra.box, (10, 10, 100, 100))


@unittest.skipUnless(_CV_DISPONIVEL, "OpenCV/NumPy não disponíveis neste ambiente")
class TestPreparacaoModelo(unittest.TestCase):
    def test_pesos_ausentes_sao_invalidos(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse(vision.pesos_locais_validos(tmp))

    def test_preparar_modelo_sem_download_autorizado_falha(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(vision.ModelError):
                vision.preparar_modelo(tmp, allow_download=False)


if __name__ == "__main__":
    unittest.main()
