"""vision.py — Aquisição, pré-processamento, segmentação e extração facial.

Dependências pesadas (OpenCV, NumPy, TensorFlow/Keras, keras-facenet) são
importadas de forma tardia, dentro das funções/métodos que realmente as
utilizam. Isso permite que o restante da aplicação (ajuda, diagnóstico e
demonstração sintética) funcione mesmo sem essas bibliotecas instaladas.

Protótipo acadêmico: este módulo não aciona fechaduras físicas nem substitui
o modelo de reconhecimento por pesos aleatórios. Quando o download automático
não está autorizado, os pesos pré-treinados devem já existir localmente e
íntegros (verificados por SHA-256).
"""

from __future__ import annotations

import hashlib
import os
import platform
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import core

MODEL_ID = "facenet-20180402-114759-v1"
MODEL_URL = (
    "https://github.com/faustomorales/keras-facenet/releases/download/"
    "v0.3.1/20180402-114759-weights.h5"
)
MODEL_SHA256 = "8b71e7045497e841c00ee568f031d1a4d30908fceadf6884aef2dec4d545202b"
MODEL_MAX_DOWNLOAD_BYTES = 150 * 1024 * 1024  # 150 MB
MODEL_DOWNLOAD_TIMEOUT_SECONDS = 30

MAX_IMAGE_FILE_BYTES = 25 * 1024 * 1024  # 25 MB
DETECTION_MAX_DIMENSION = 1280

HAAR_SCALE_FACTOR = 1.1
HAAR_MIN_NEIGHBORS = 5
HAAR_MIN_SIZE = (40, 40)
MIN_FACE_DIMENSION_PX = 80

MIN_SHARPNESS = 60.0
BRIGHTNESS_MIN = 40.0
BRIGHTNESS_MAX = 215.0

EMBEDDING_INPUT_SIZE = 160
EMBEDDING_DIMENSIONS = 512


class FaceError(Exception):
    """Falha no pipeline de aquisição/detecção/extração facial.

    O atributo `reason` usa os identificadores de motivo definidos em core.py
    (ex.: core.RAZAO_NENHUM_ROSTO) para que AccessService.attempt(failure=...)
    possa negar o acesso de forma consistente.
    """

    def __init__(self, reason: str, message: Optional[str] = None):
        self.reason = reason
        super().__init__(message or reason)


class ModelError(Exception):
    """Falha ao preparar/validar os pesos do modelo de extração facial."""


# ---------------------------------------------------------------------------
# 5.1 Aquisição
# ---------------------------------------------------------------------------


class Webcam:
    """Wrapper de aquisição via OpenCV VideoCapture.

    Uso recomendado como gerenciador de contexto, garantindo a liberação do
    dispositivo ao sair do bloco `with`.
    """

    def __init__(self, index: int = 0):
        self.index = index
        self._cap = None

    def __enter__(self) -> "Webcam":
        self._open()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _open(self) -> None:
        import cv2  # import tardio

        backend = cv2.CAP_DSHOW if platform.system() == "Windows" else cv2.CAP_ANY
        self._cap = cv2.VideoCapture(self.index, backend)
        if not self._cap.isOpened():
            self._cap.release()
            self._cap = None
            raise FaceError(
                core.RAZAO_CAMERA_INDISPONIVEL,
                f"Não foi possível abrir a câmera de índice {self.index}",
            )

    def read(self):
        """Lê um quadro. Retorna array NumPy BGR uint8, ou None em falha de leitura."""
        if self._cap is None:
            self._open()
        ok, frame = self._cap.read()
        if not ok:
            return None
        return frame

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None


def load_image(path: "str | Path"):
    """Carrega uma imagem de arquivo (scanner ou câmera externa) como BGR uint8.

    Suporta caminhos Unicode via np.fromfile + cv2.imdecode. Rejeita arquivo
    inexistente, inválido ou maior que 25 MB.
    """
    import cv2  # import tardio
    import numpy as np  # import tardio

    caminho = Path(path)
    if not caminho.is_file():
        raise FaceError(core.RAZAO_NENHUM_ROSTO, f"Arquivo não encontrado: {caminho}")

    tamanho = caminho.stat().st_size
    if tamanho == 0 or tamanho > MAX_IMAGE_FILE_BYTES:
        raise FaceError(
            core.RAZAO_NENHUM_ROSTO,
            f"Arquivo de imagem inválido ou maior que 25 MB: {caminho}",
        )

    dados = np.fromfile(str(caminho), dtype=np.uint8)
    imagem = cv2.imdecode(dados, cv2.IMREAD_COLOR)
    if imagem is None or imagem.size == 0:
        raise FaceError(core.RAZAO_NENHUM_ROSTO, f"Não foi possível decodificar a imagem: {caminho}")
    return imagem


# ---------------------------------------------------------------------------
# Preparação e integridade do modelo
# ---------------------------------------------------------------------------


def _sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def pesos_locais_validos(models_dir: "str | Path") -> bool:
    caminho = Path(models_dir) / "20180402-114759-weights.h5"
    if not caminho.is_file():
        return False
    return _sha256_arquivo(caminho) == MODEL_SHA256


def preparar_modelo(models_dir: "str | Path", allow_download: bool = False) -> Path:
    """Garante que os pesos pré-treinados estejam disponíveis e íntegros.

    Reutiliza pesos locais válidos. Rejeita pesos locais com hash inválido sem
    sobrescrevê-los automaticamente. Só baixa quando allow_download=True
    (comando explícito `preparar-modelo` ou autorização explícita na API).
    """
    models_dir = Path(models_dir)
    destino = models_dir / "20180402-114759-weights.h5"

    if destino.is_file():
        if _sha256_arquivo(destino) == MODEL_SHA256:
            return destino
        if not allow_download:
            raise ModelError(
                f"Pesos locais em {destino} têm hash inválido. "
                "Não foram sobrescritos automaticamente; remova-os manualmente "
                "ou execute 'preparar-modelo' explicitamente."
            )
        # allow_download=True: será tentado um novo download abaixo, sem
        # jamais sobrescrever o arquivo existente antes de validar o novo.

    if not allow_download:
        raise ModelError(
            "Pesos do modelo ausentes ou inválidos e download não autorizado. "
            "Execute o comando 'preparar-modelo' ou informe allow_download=True."
        )

    models_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp_nome = tempfile.mkstemp(prefix="facenet_download_", suffix=".tmp", dir=str(models_dir))
    tmp_caminho = Path(tmp_nome)
    os.close(fd)
    try:
        with urllib.request.urlopen(MODEL_URL, timeout=MODEL_DOWNLOAD_TIMEOUT_SECONDS) as resposta:
            total = 0
            with tmp_caminho.open("wb") as f:
                while True:
                    bloco = resposta.read(1024 * 1024)
                    if not bloco:
                        break
                    total += len(bloco)
                    if total > MODEL_MAX_DOWNLOAD_BYTES:
                        raise ModelError("Download excedeu o limite de 150 MB")
                    f.write(bloco)

        if _sha256_arquivo(tmp_caminho) != MODEL_SHA256:
            raise ModelError(
                "SHA-256 do arquivo baixado não confere com o valor esperado; "
                "download descartado."
            )
        tmp_caminho.replace(destino)
        return destino
    except Exception:
        if tmp_caminho.exists():
            tmp_caminho.unlink(missing_ok=True)
        raise
    finally:
        if tmp_caminho.exists():
            tmp_caminho.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# 5.4 Extração de características — FaceSample e embutidor FaceNet
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Quality:
    sharpness: float
    brightness: float


@dataclass(frozen=True)
class FaceSample:
    embedding: list
    box: Tuple[int, int, int, int]  # x, y, largura, altura
    quality: Quality


class _FaceEmbedder:
    """Carrega o modelo FaceNet/InceptionResNetV1 (pesos 20180402-114759)."""

    def __init__(self, weights_path: Path):
        import tensorflow as tf  # import tardio

        self._modelo = tf.keras.models.load_model(str(weights_path), compile=False)

    def embed(self, face_rgb_160):
        import numpy as np  # import tardio

        entrada = face_rgb_160.astype("float32")
        entrada = (entrada - 127.5) / 127.5
        entrada = np.expand_dims(entrada, axis=0)
        saida = self._modelo(entrada, training=False)
        vetor = np.asarray(saida)[0].astype("float64").tolist()
        if len(vetor) != EMBEDDING_DIMENSIONS:
            raise ModelError(
                f"Saída do modelo com dimensão inesperada: {len(vetor)} "
                f"(esperado {EMBEDDING_DIMENSIONS})"
            )
        return vetor


# ---------------------------------------------------------------------------
# Pipeline completo (5.2 pré-processamento, 5.3 segmentação, 5.4 extração)
# ---------------------------------------------------------------------------


class FacePipeline:
    """Executa as cinco fases sobre uma imagem BGR e produz um FaceSample."""

    def __init__(self, models_dir: "str | Path" = "models", allow_download: bool = False):
        self.models_dir = Path(models_dir)
        self.allow_download = allow_download
        self._embedder: Optional[_FaceEmbedder] = None
        self._cascade = None

    def _garantir_modelo(self) -> _FaceEmbedder:
        if self._embedder is None:
            caminho_pesos = preparar_modelo(self.models_dir, allow_download=self.allow_download)
            self._embedder = _FaceEmbedder(caminho_pesos)
        return self._embedder

    def _garantir_cascade(self):
        import cv2  # import tardio

        if self._cascade is None:
            caminho = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            cascade = cv2.CascadeClassifier(caminho)
            if cascade.empty():
                raise FaceError(core.RAZAO_NENHUM_ROSTO, "Não foi possível carregar o Haar Cascade")
            self._cascade = cascade
        return self._cascade

    def extract(self, imagem) -> FaceSample:
        import cv2  # import tardio
        import numpy as np  # import tardio

        if imagem is None or not isinstance(imagem, np.ndarray):
            raise FaceError(core.RAZAO_NENHUM_ROSTO, "Imagem inválida: esperado array NumPy")
        if imagem.dtype != np.uint8 or imagem.ndim != 3 or imagem.shape[2] != 3:
            raise FaceError(
                core.RAZAO_NENHUM_ROSTO,
                "Imagem inválida: esperado BGR uint8 com três canais",
            )
        if imagem.size == 0:
            raise FaceError(core.RAZAO_NENHUM_ROSTO, "Imagem vazia")

        altura_orig, largura_orig = imagem.shape[:2]

        # 5.2 Pré-processamento (somente no ramo de detecção)
        maior_lado = max(altura_orig, largura_orig)
        escala = 1.0
        if maior_lado > DETECTION_MAX_DIMENSION:
            escala = DETECTION_MAX_DIMENSION / float(maior_lado)
        largura_det = max(1, int(round(largura_orig * escala)))
        altura_det = max(1, int(round(altura_orig * escala)))
        imagem_deteccao = (
            cv2.resize(imagem, (largura_det, altura_det), interpolation=cv2.INTER_AREA)
            if escala != 1.0
            else imagem
        )

        cinza = cv2.cvtColor(imagem_deteccao, cv2.COLOR_BGR2GRAY)
        cinza_suave = cv2.GaussianBlur(cinza, (3, 3), 0)
        cinza_equalizada = cv2.equalizeHist(cinza_suave)

        # 5.3 Segmentação
        cascade = self._garantir_cascade()
        deteccoes = cascade.detectMultiScale(
            cinza_equalizada,
            scaleFactor=HAAR_SCALE_FACTOR,
            minNeighbors=HAAR_MIN_NEIGHBORS,
            minSize=HAAR_MIN_SIZE,
        )

        if len(deteccoes) == 0:
            raise FaceError(core.RAZAO_NENHUM_ROSTO, "Nenhum rosto detectado")
        if len(deteccoes) > 1:
            raise FaceError(
                core.RAZAO_MULTIPLOS_ROSTOS,
                f"Múltiplos rostos detectados ({len(deteccoes)}); operação negada",
            )

        x_d, y_d, w_d, h_d = deteccoes[0]
        # Converte coordenadas da imagem de detecção (redimensionada) para a original.
        x = int(round(x_d / escala))
        y = int(round(y_d / escala))
        w = int(round(w_d / escala))
        h = int(round(h_d / escala))

        # Limita o recorte aos limites da imagem original.
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(largura_orig, x + w)
        y1 = min(altura_orig, y + h)
        w_final = x1 - x0
        h_final = y1 - y0

        if w_final < MIN_FACE_DIMENSION_PX or h_final < MIN_FACE_DIMENSION_PX:
            raise FaceError(
                core.RAZAO_ROSTO_PEQUENO,
                f"Rosto detectado é pequeno demais ({w_final}x{h_final}px)",
            )

        recorte_bgr = imagem[y0:y1, x0:x1]

        # Verificações de qualidade do recorte (nitidez e luminosidade)
        recorte_cinza = cv2.cvtColor(recorte_bgr, cv2.COLOR_BGR2GRAY)
        nitidez = float(cv2.Laplacian(recorte_cinza, cv2.CV_64F).var())
        luminosidade = float(recorte_cinza.mean())

        if nitidez < MIN_SHARPNESS:
            raise FaceError(
                core.RAZAO_IMAGEM_DESFOCADA,
                f"Nitidez insuficiente ({nitidez:.1f} < {MIN_SHARPNESS})",
            )
        if not (BRIGHTNESS_MIN <= luminosidade <= BRIGHTNESS_MAX):
            raise FaceError(
                core.RAZAO_ILUMINACAO_INADEQUADA,
                f"Luminosidade fora da faixa aceitável ({luminosidade:.1f})",
            )

        # 5.4 Extração de características (usa o recorte BGR original, sem as
        # transformações de detecção, preservando o pré-processamento do FaceNet)
        recorte_rgb = cv2.cvtColor(recorte_bgr, cv2.COLOR_BGR2RGB)
        recorte_160 = cv2.resize(
            recorte_rgb, (EMBEDDING_INPUT_SIZE, EMBEDDING_INPUT_SIZE), interpolation=cv2.INTER_LINEAR
        )

        embedder = self._garantir_modelo()
        vetor_bruto = embedder.embed(recorte_160)
        vetor_normalizado = core._l2_normalizar(vetor_bruto)

        return FaceSample(
            embedding=vetor_normalizado,
            box=(x0, y0, w_final, h_final),
            quality=Quality(sharpness=nitidez, brightness=luminosidade),
        )
