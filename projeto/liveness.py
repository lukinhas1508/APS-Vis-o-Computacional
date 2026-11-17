"""liveness.py — Prova de vida ATIVA (desafio-resposta) para a versão desktop.

Por que a versão anterior aceitava uma foto do celular: não havia nenhuma
prova de vida — qualquer imagem com um rosto parecido era aceita (inclusive
arquivos importados). Diferenças entre quadros também não provam vida: basta
balançar o celular na frente da câmera.

Como funciona agora:
  1. O MediaPipe Face Mesh rastreia 468 pontos do rosto a cada quadro.
  2. Um desafio ALEATÓRIO de 3 etapas é sorteado (sempre "piscar" + 2 entre
     "virar à esquerda", "virar à direita" e "abrir a boca").
  3. Cada etapa exige: rosto de frente → executar a ação → voltar de frente,
     dentro de um tempo limite.
  4. O giro é medido pela posição da ponta do nariz RELATIVA aos cantos dos
     olhos (paralaxe 3D). Inclinar ou balançar uma foto plana não muda essa
     relação; uma cabeça real girando muda.
  5. A aprovação vale só enquanto o MESMO rosto continua no quadro: se o rosto
     sumir, aparecer um segundo rosto ou houver troca brusca, tudo recomeça.
     A aprovação também expira (SESSION_TTL_S).

Uma foto (impressa ou na tela) não pisca, não abre a boca e não gira com
paralaxe — portanto nunca é aprovada. Limitação conhecida (protótipo): um
vídeo/deepfake em tempo real controlado por um atacante não é coberto.

A máquina de estados (LivenessSession) é Python puro e testável; apenas
FaceMeshTracker importa mediapipe/OpenCV (import tardio).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

FRONTAL_MAX = 0.07       # |giro - 0.5| abaixo disso = rosto de frente
TURN_MIN = 0.12          # |giro - 0.5| acima disso  = cabeça girada
EAR_CLOSED = 0.17        # razão de aspecto do olho: fechado
EAR_OPEN = 0.21          # razão de aspecto do olho: aberto
MAR_OPEN = 0.45          # abertura interna da boca / largura da boca: aberta
MAR_CLOSED = 0.20        # idem: fechada (sorriso com lábios entreabertos ~0.18)
MIN_FACE_SIZE = 0.18     # largura mínima do rosto (fração do quadro)
STEP_TIMEOUT_S = 8.0     # tempo máximo por etapa
SESSION_TTL_S = 20.0     # validade da prova de vida aprovada
MAX_GAP_S = 0.7          # rosto sumiu por mais que isso → recomeça
MAX_JUMP = 0.18          # salto do centro do rosto entre quadros → recomeça
RETRY_DELAY_S = 2.0      # espera após reprovação
STEPS = 3

CHALLENGES = {
    "blink": "Pisque os olhos",
    "left": "Vire o rosto para a sua esquerda",
    "right": "Vire o rosto para a sua direita",
    "mouth": "Abra a boca",
}

REASON_TEXT = {
    "rosto_perdido": "Rosto saiu do quadro — desafio reiniciado",
    "multiplos_rostos": "Mais de um rosto no quadro — desafio reiniciado",
    "rosto_trocado": "Mudança brusca de rosto — desafio reiniciado",
    "tempo_esgotado": "Tempo esgotado — novo desafio em instantes",
    "desafio_incorreto": "Movimento incorreto — novo desafio em instantes",
    "prova_de_vida_expirada": "Prova de vida expirada — refaça o desafio",
}

# Índices do Face Mesh (468 pontos)
IDX_NOSE_TIP = 1
IDX_EYE_R = (33, 160, 158, 133, 153, 144)    # olho direito da pessoa
IDX_EYE_L = (263, 387, 385, 362, 380, 373)   # olho esquerdo da pessoa
IDX_MOUTH = (13, 14, 78, 308)                # lábio sup., lábio inf., cantos


# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FaceMetrics:
    faces: int
    yaw: float = 0.5
    ear: float = 0.3
    mar: float = 0.0
    center: Tuple[float, float] = (0.5, 0.5)
    size: float = 0.0
    box: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)  # x, y, w, h (normalizados)


def _dist(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _ear(pts, idx) -> float:
    p1, p2, p3, p4, p5, p6 = (pts[i] for i in idx)
    horizontal = _dist(p1, p4)
    if horizontal < 1e-9:
        return 0.0
    return (_dist(p2, p6) + _dist(p3, p5)) / (2.0 * horizontal)


def metrics_from_landmarks(
    faces: Sequence[Sequence[Tuple[float, float]]], aspect: float = 1.0
) -> FaceMetrics:
    """Converte listas de pontos normalizados (x, y) em FaceMetrics.

    aspect = largura / altura do quadro (corrige a escala de x para que as
    distâncias e a projeção do giro fiquem em pixels "quadrados").
    """
    if len(faces) != 1:
        return FaceMetrics(faces=len(faces))
    bruto = faces[0]
    xs = [p[0] for p in bruto]
    ys = [p[1] for p in bruto]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    pts = [(p[0] * aspect, p[1]) for p in bruto]

    # Giro = projeção da ponta do nariz sobre o eixo entre os cantos externos
    # dos olhos (0 = olho direito, 1 = olho esquerdo). Projetar no eixo dos
    # olhos torna a métrica imune a girar o celular no plano (roll).
    eye_r, eye_l, nose = pts[IDX_EYE_R[0]], pts[IDX_EYE_L[0]], pts[IDX_NOSE_TIP]
    ex, ey = eye_l[0] - eye_r[0], eye_l[1] - eye_r[1]
    d2 = ex * ex + ey * ey
    yaw = 0.5 if d2 < 1e-12 else ((nose[0] - eye_r[0]) * ex + (nose[1] - eye_r[1]) * ey) / d2

    ear = (_ear(pts, IDX_EYE_R) + _ear(pts, IDX_EYE_L)) / 2.0
    up, low, c1, c2 = (pts[i] for i in IDX_MOUTH)
    largura = _dist(c1, c2)
    mar = 0.0 if largura < 1e-9 else _dist(up, low) / largura

    return FaceMetrics(
        faces=1,
        yaw=yaw,
        ear=ear,
        mar=mar,
        center=((min_x + max_x) / 2.0, (min_y + max_y) / 2.0),
        size=max_x - min_x,
        box=(min_x, min_y, max_x - min_x, max_y - min_y),
    )


def is_neutral(m: FaceMetrics) -> bool:
    return abs(m.yaw - 0.5) < FRONTAL_MAX and m.ear > EAR_OPEN and m.mar < MAR_CLOSED


def did_action(ch: str, m: FaceMetrics) -> bool:
    """giro > 0.5 = pessoa virou para a ESQUERDA DELA (quadro não espelhado)."""
    if ch == "blink":
        return m.ear < EAR_CLOSED
    if ch == "left":
        return (m.yaw - 0.5) > TURN_MIN
    if ch == "right":
        return (0.5 - m.yaw) > TURN_MIN
    if ch == "mouth":
        return m.mar > MAR_OPEN
    return False


def _opposite(ch: str) -> Optional[str]:
    return {"left": "right", "right": "left"}.get(ch)


_RNG_SEGURO = random.SystemRandom()


def new_sequence(rand: Callable[[], float] = _RNG_SEGURO.random) -> List[str]:
    rng = random.Random(rand())
    outros = ["left", "right", "mouth"]
    rng.shuffle(outros)
    seq = ["blink"] + outros[: STEPS - 1]
    rng.shuffle(seq)
    return seq


# ---------------------------------------------------------------------------
# Máquina de estados
# ---------------------------------------------------------------------------

_proximo_id = 0


def _novo_id() -> int:
    global _proximo_id
    _proximo_id += 1
    return _proximo_id


@dataclass
class LivenessSession:
    """Estado da prova de vida. Chame step(métricas, agora) a cada quadro."""

    now: float
    rand: Callable[[], float] = _RNG_SEGURO.random
    reason: Optional[str] = None
    id: int = field(default_factory=_novo_id)
    status: str = "aguardando_rosto"  # aguardando_rosto | desafio | aprovado | reprovado
    seq: List[str] = field(default_factory=list)
    idx: int = 0
    phase: str = "neutral"            # neutral → action → return
    step_start: float = 0.0
    last_seen: Optional[float] = None
    last_center: Optional[Tuple[float, float]] = None
    passed_at: Optional[float] = None
    failed_at: Optional[float] = None
    hint: Optional[str] = None

    def __post_init__(self) -> None:
        if not self.seq:
            self.seq = new_sequence(self.rand)
        self.step_start = self.now

    # -- reinício ---------------------------------------------------------
    def _reiniciar(self, now: float, reason: Optional[str]) -> None:
        novo = LivenessSession(now=now, rand=self.rand, reason=reason)
        self.__dict__.update(novo.__dict__)

    # -- consulta ---------------------------------------------------------
    def vivo_e_presente(self, now: float) -> bool:
        return (
            self.status == "aprovado"
            and self.passed_at is not None
            and now - self.passed_at <= SESSION_TTL_S
            and self.last_seen is not None
            and now - self.last_seen <= MAX_GAP_S
        )

    def instrucao(self) -> str:
        if self.status == "aprovado":
            return "Prova de vida aprovada"
        if self.status == "reprovado":
            return REASON_TEXT.get(self.reason or "", "Prova de vida reprovada")
        if self.status == "aguardando_rosto":
            return self.hint or "Posicione o rosto na câmera"
        if self.phase == "neutral":
            return "Olhe de frente para a câmera"
        return CHALLENGES[self.seq[min(self.idx, len(self.seq) - 1)]]

    def progresso(self) -> str:
        if self.status in ("desafio", "aprovado"):
            return f"{min(self.idx + (0 if self.status == 'aprovado' else 1), len(self.seq))}/{len(self.seq)}"
        return ""

    # -- transição --------------------------------------------------------
    def step(self, m: Optional[FaceMetrics], now: float) -> "LivenessSession":
        if self.status == "reprovado":
            if now - (self.failed_at or now) >= RETRY_DELAY_S:
                self._reiniciar(now, self.reason)
            return self

        if m is None or m.faces == 0:
            if self.last_seen is not None and now - self.last_seen > MAX_GAP_S:
                self._reiniciar(now, "rosto_perdido")
            elif self.last_seen is None:
                self.hint = "Posicione o rosto na câmera"
            return self

        if m.faces > 1:
            self._reiniciar(now, "multiplos_rostos")
            return self

        if self.last_center is not None and self.last_seen is not None:
            if _dist(m.center, self.last_center) > MAX_JUMP:
                self._reiniciar(now, "rosto_trocado")
                return self
            if now - self.last_seen > MAX_GAP_S:
                self._reiniciar(now, "rosto_perdido")
                return self

        self.last_seen = now
        self.last_center = m.center
        self.hint = None

        if m.size < MIN_FACE_SIZE:
            self.hint = "Aproxime o rosto da câmera"
            if self.status != "desafio":
                self.step_start = now
            return self

        if self.status == "aprovado":
            if now - (self.passed_at or now) > SESSION_TTL_S:
                centro = m.center
                self._reiniciar(now, "prova_de_vida_expirada")
                self.status = "desafio"
                self.last_seen = now
                self.last_center = centro
            return self

        if self.status == "aguardando_rosto":
            self.status = "desafio"
            self.step_start = now
            self.phase = "neutral"

        if now - self.step_start > STEP_TIMEOUT_S:
            self.status, self.failed_at, self.reason = "reprovado", now, "tempo_esgotado"
            return self

        ch = self.seq[self.idx]
        opp = _opposite(ch)
        if opp and self.phase != "return" and did_action(opp, m):
            self.status, self.failed_at, self.reason = "reprovado", now, "desafio_incorreto"
            return self

        if self.phase == "neutral":
            if is_neutral(m):
                self.phase = "action"
            else:
                self.hint = "Olhe de frente, olhos abertos e boca fechada"
        elif self.phase == "action":
            if did_action(ch, m):
                self.phase = "return"
        elif self.phase == "return":
            if is_neutral(m):
                self.idx += 1
                if self.idx >= len(self.seq):
                    self.status, self.passed_at, self.reason = "aprovado", now, None
                else:
                    self.phase, self.step_start = "action", now
            else:
                self.hint = "Volte a olhar de frente"
        return self


# ---------------------------------------------------------------------------
# Rastreador (MediaPipe Face Mesh — modelo embutido no pacote pip)
# ---------------------------------------------------------------------------


class LivenessUnavailable(Exception):
    """MediaPipe não instalado/indisponível: o sistema deve falhar fechado."""


class FaceMeshTracker:
    def __init__(self) -> None:
        try:
            import mediapipe as mp  # import tardio
        except Exception as exc:  # noqa: BLE001
            raise LivenessUnavailable(
                "mediapipe não está instalado — prova de vida indisponível; acesso bloqueado. "
                "Instale com: pip install mediapipe==0.10.14"
            ) from exc
        self._mesh = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=2,           # 2 para detectar (e negar) múltiplos rostos
            refine_landmarks=False,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.6,
        )

    def process(self, imagem_bgr) -> FaceMetrics:
        import cv2  # import tardio

        rgb = cv2.cvtColor(imagem_bgr, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        res = self._mesh.process(rgb)
        faces = []
        for face in res.multi_face_landmarks or []:
            faces.append([(p.x, p.y) for p in face.landmark])
        h, w = imagem_bgr.shape[:2]
        return metrics_from_landmarks(faces, aspect=w / float(h))

    def close(self) -> None:
        self._mesh.close()

    def __enter__(self) -> "FaceMeshTracker":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def desenhar_instrucao(quadro, sessao: LivenessSession):
    """Escreve a instrução do desafio no quadro (cópia). Sem acentos: cv2.putText não suporta Unicode."""
    import unicodedata

    import cv2  # import tardio

    saida = quadro.copy()
    texto = sessao.instrucao()
    prog = sessao.progresso()
    if prog:
        texto = f"[{prog}] {texto}"
    if sessao.hint and sessao.status == "desafio":
        texto += f" - {sessao.hint}"
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    cor = {"aprovado": (40, 170, 60), "reprovado": (40, 40, 200)}.get(sessao.status, (0, 160, 230))
    h, w = saida.shape[:2]
    cv2.rectangle(saida, (0, h - 40), (w, h), (20, 20, 20), -1)
    cv2.putText(saida, texto, (10, h - 13), cv2.FONT_HERSHEY_SIMPLEX, 0.6, cor, 2, cv2.LINE_AA)
    return saida
