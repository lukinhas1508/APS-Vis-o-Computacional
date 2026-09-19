"""core.py — Regras de negócio, entidades e persistência do Cofre Acadêmico.

Este módulo depende SOMENTE da biblioteca padrão do Python (sqlite3, dataclasses,
datetime, json, math, csv, pathlib, etc.). Nenhuma dependência de visão
computacional ou aprendizado de máquina deve ser importada aqui, para que
ajuda, diagnóstico e demonstração sintética funcionem sem TensorFlow/OpenCV.

Protótipo acadêmico. Todas as autorizações são SIMULADAS: nenhuma fechadura
física é acionada e nenhum sistema governamental real é acessado.
"""

from __future__ import annotations

import csv
import json
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Constantes de domínio
# ---------------------------------------------------------------------------

ID_DESCONHECIDO = "desconhecido"

# Motivos (seção 14 + complementos de autorização)
RAZAO_AUTORIZADO = "autorizado"
RAZAO_SEM_NIVEL = "sem_autorizacao_nivel"
RAZAO_DESCONHECIDO = "desconhecido"
RAZAO_AMBIGUO = "identidade_ambigua"
RAZAO_GALERIA_VAZIA = "galeria_vazia"

# Motivos de falha de processamento de imagem (originados em vision.py,
# mas os identificadores textuais vivem aqui para manter core.py autônomo).
RAZAO_NENHUM_ROSTO = "nenhum_rosto"
RAZAO_MULTIPLOS_ROSTOS = "multiplos_rostos"
RAZAO_ROSTO_PEQUENO = "rosto_pequeno"
RAZAO_IMAGEM_DESFOCADA = "imagem_desfocada"
RAZAO_ILUMINACAO_INADEQUADA = "iluminacao_inadequada"
RAZAO_CAMERA_INDISPONIVEL = "camera_indisponivel"

FONTES_VALIDAS = ("webcam", "imagem", "simulacao", "avaliacao")

# Dimensões conhecidas por identificador de modelo (para validar embeddings).
DIMENSOES_MODELO_CONHECIDAS = {
    "facenet-20180402-114759-v1": 512,
}


class ErroDominio(Exception):
    """Erro de validação de regra de negócio (entrada inválida do operador)."""


# ---------------------------------------------------------------------------
# Entidades
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class User:
    id: str
    name: str
    level: int
    division: str


@dataclass(frozen=True)
class Area:
    name: str
    level: int
    division: str = ""


@dataclass(frozen=True)
class Decision:
    user_id: Optional[str]
    user_name: str
    user_level: Optional[int]
    area: str
    granted: bool
    reason: str
    distance: Optional[float]


AREAS: Dict[str, Area] = {
    "geral": Area(name="Consulta geral", level=1, division=""),
    "toxinas": Area(name="Registros de toxinas", level=2, division="Toxinas"),
    "fiscalizacao": Area(name="Registros de fiscalização", level=2, division="Fiscalização"),
    "ministerial": Area(name="Gabinete ministerial", level=3, division=""),
}

DIVISOES_VALIDAS = ("Toxinas", "Fiscalização")


def area_valida(chave: str) -> bool:
    return chave in AREAS


def is_authorized(user: Optional[User], area_key: str) -> bool:
    """Aplica as regras de autorização descritas na seção 7."""
    if area_key not in AREAS:
        raise ErroDominio(f"Área desconhecida: {area_key!r}")
    if user is None:
        return False
    area = AREAS[area_key]
    if user.level == 1:
        return area.level == 1
    if user.level == 2:
        if area.level == 1:
            return True
        if area.level == 2:
            return user.division == area.division
        return False
    if user.level == 3:
        return True
    return False


def _utc_agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validar_embedding(vector: Sequence, model_id: str) -> List[float]:
    """Valida e normaliza um embedding cru vindo de fora, levantando ErroDominio."""
    if vector is None:
        raise ErroDominio("Embedding vazio ou ausente")
    try:
        valores = [float(v) for v in vector]
    except (TypeError, ValueError, OverflowError):
        raise ErroDominio("Embedding contém valores não numéricos ou fora de faixa")
    if not valores:
        raise ErroDominio("Embedding vazio")
    if any(not math.isfinite(v) for v in valores):
        raise ErroDominio("Embedding contém valores não finitos (NaN/Inf)")
    norma = math.sqrt(sum(v * v for v in valores))
    if norma == 0.0:
        raise ErroDominio("Embedding com norma zero")
    dimensao_esperada = DIMENSOES_MODELO_CONHECIDAS.get(model_id)
    if dimensao_esperada is not None and len(valores) != dimensao_esperada:
        raise ErroDominio(
            f"Dimensão de embedding incompatível com o modelo {model_id!r}: "
            f"esperado {dimensao_esperada}, recebido {len(valores)}"
        )
    return valores


def _l2_normalizar(valores: Sequence[float]) -> List[float]:
    norma = math.sqrt(sum(v * v for v in valores))
    if norma == 0.0:
        raise ErroDominio("Embedding com norma zero")
    return [v / norma for v in valores]


def _distancia_euclidiana(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise ErroDominio("Embeddings com dimensões incompatíveis na comparação")
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _neutralizar_celula_csv(valor: str) -> str:
    """Evita que valores textuais virem fórmulas ao abrir o CSV em planilhas."""
    if valor and valor[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + valor
    return valor


# ---------------------------------------------------------------------------
# Persistência SQLite
# ---------------------------------------------------------------------------


_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    level INTEGER NOT NULL CHECK(level BETWEEN 1 AND 3),
    division TEXT NOT NULL,
    consent_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_users_unico_ministro
    ON users(level) WHERE level = 3;

CREATE TABLE IF NOT EXISTS embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    model TEXT NOT NULL,
    vector TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    user_id TEXT,
    user_name TEXT NOT NULL,
    user_level INTEGER,
    area TEXT NOT NULL,
    granted INTEGER NOT NULL,
    reason TEXT NOT NULL,
    distance REAL,
    source TEXT NOT NULL,
    simulated INTEGER NOT NULL
);
"""


class Store:
    """Camada de persistência SQLite. Uso restrito à thread principal."""

    def __init__(self, path: "str | Path"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path))
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # -- usuários -----------------------------------------------------

    def users(self) -> List[User]:
        cur = self._conn.execute("SELECT id, name, level, division FROM users ORDER BY id")
        return [User(id=r[0], name=r[1], level=r[2], division=r[3]) for r in cur.fetchall()]

    def get_user(self, user_id: str) -> Optional[User]:
        cur = self._conn.execute(
            "SELECT id, name, level, division FROM users WHERE id = ?", (user_id,)
        )
        row = cur.fetchone()
        if row is None:
            return None
        return User(id=row[0], name=row[1], level=row[2], division=row[3])

    def enroll(
        self,
        user_id: str,
        name: str,
        level: int,
        division: str,
        consentimento: bool,
        model_id: str,
        embeddings: Iterable[Sequence[float]],
    ) -> User:
        """Cadastra usuário e embeddings em uma única transação. Reverte tudo em falha."""
        user_id = (user_id or "").strip()
        name = (name or "").strip()
        division = (division or "").strip()

        if not consentimento:
            raise ErroDominio("Consentimento explícito é obrigatório para cadastro")
        if not user_id:
            raise ErroDominio("ID não pode ser vazio")
        if user_id == ID_DESCONHECIDO:
            raise ErroDominio(f"ID reservado {ID_DESCONHECIDO!r} não pode ser usado")
        if not name:
            raise ErroDominio("Nome não pode ser vazio")
        if level not in (1, 2, 3):
            raise ErroDominio("Nível deve ser 1, 2 ou 3")
        if level == 2 and division not in DIVISOES_VALIDAS:
            raise ErroDominio(
                f"Divisão válida obrigatória para nível 2 (uma de {DIVISOES_VALIDAS})"
            )
        if level != 2:
            division = ""

        embeddings_validados: List[List[float]] = []
        for vetor in embeddings:
            embeddings_validados.append(_validar_embedding(vetor, model_id))
        if len(embeddings_validados) < 3:
            raise ErroDominio("São necessários pelo menos três embeddings válidos")

        if self.get_user(user_id) is not None:
            raise ErroDominio(
                f"ID {user_id!r} já cadastrado; não é permitido sobrescrever cadastro existente"
            )

        consent_at = _utc_agora_iso()
        try:
            with self._conn:
                self._conn.execute(
                    "INSERT INTO users (id, name, level, division, consent_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (user_id, name, level, division, consent_at),
                )
                for vetor in embeddings_validados:
                    self._conn.execute(
                        "INSERT INTO embeddings (user_id, model, vector) VALUES (?, ?, ?)",
                        (user_id, model_id, json.dumps(vetor)),
                    )
        except sqlite3.IntegrityError as exc:
            raise ErroDominio(f"Falha de integridade ao cadastrar: {exc}") from exc

        return User(id=user_id, name=name, level=level, division=division)

    # -- galeria de embeddings -----------------------------------------

    def gallery(self, model_id: str) -> Dict[str, List[List[float]]]:
        """Retorna {user_id: [vetores]} isolado pelo identificador do modelo."""
        cur = self._conn.execute(
            "SELECT user_id, vector FROM embeddings WHERE model = ?", (model_id,)
        )
        galeria: Dict[str, List[List[float]]] = {}
        for user_id, vector_json in cur.fetchall():
            vetor = json.loads(vector_json)
            galeria.setdefault(user_id, []).append(vetor)
        return galeria

    # -- auditoria -------------------------------------------------------

    def log(self, decision: Decision, source: str, simulated: bool) -> None:
        if source not in FONTES_VALIDAS:
            raise ErroDominio(f"Origem inválida: {source!r}")
        if source == "simulacao":
            # source=simulacao deve sempre resultar em simulated=1.
            simulated = True
        with self._conn:
            self._conn.execute(
                "INSERT INTO attempts "
                "(timestamp, user_id, user_name, user_level, area, granted, reason, "
                " distance, source, simulated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    _utc_agora_iso(),
                    decision.user_id,
                    decision.user_name,
                    decision.user_level,
                    decision.area,
                    1 if decision.granted else 0,
                    decision.reason,
                    decision.distance,
                    source,
                    1 if simulated else 0,
                ),
            )

    def attempts(self) -> List[dict]:
        cur = self._conn.execute(
            "SELECT timestamp, user_id, user_name, user_level, area, granted, reason, "
            "distance, source, simulated FROM attempts ORDER BY id"
        )
        colunas = [
            "timestamp", "user_id", "user_name", "user_level", "area", "granted",
            "reason", "distance", "source", "simulated",
        ]
        return [dict(zip(colunas, row)) for row in cur.fetchall()]

    # -- exportação --------------------------------------------------

    def export(self, destino: "str | Path") -> Path:
        destino = Path(destino)
        if destino.resolve() == self.path.resolve():
            raise ErroDominio(
                "Não é permitido exportar sobre o próprio arquivo do banco SQLite"
            )
        destino.parent.mkdir(parents=True, exist_ok=True)
        registros = self.attempts()
        with destino.open("w", newline="", encoding="utf-8-sig") as f:
            escritor = csv.writer(f)
            cabecalho = [
                "timestamp", "user_id", "user_name", "user_level", "area", "granted",
                "reason", "distance", "source", "simulated",
            ]
            escritor.writerow(cabecalho)
            for reg in registros:
                linha = []
                for campo in cabecalho:
                    valor = reg[campo]
                    if isinstance(valor, str):
                        valor = _neutralizar_celula_csv(valor)
                    linha.append("" if valor is None else valor)
                escritor.writerow(linha)
        return destino


# ---------------------------------------------------------------------------
# Serviço de acesso
# ---------------------------------------------------------------------------


class AccessService:
    """Identificação por menor distância euclidiana + autorização simulada."""

    def __init__(
        self,
        store: Store,
        model_id: str,
        threshold: float = 0.8,
        margin: float = 0.1,
    ):
        if not math.isfinite(threshold) or not (0 < threshold < 2):
            raise ErroDominio("Limiar deve ser finito e estar estritamente entre 0 e 2")
        if not math.isfinite(margin) or not (0 < margin < 2):
            raise ErroDominio("Margem deve ser finita e estar estritamente entre 0 e 2")
        self.store = store
        self.model_id = model_id
        self.threshold = threshold
        self.margin = margin

    def identify(
        self, vector: Sequence[float]
    ) -> Tuple[Optional[User], Optional[float], str]:
        """Retorna (usuário ou None, distância ou None, motivo)."""
        consulta = _l2_normalizar(_validar_embedding(vector, self.model_id))
        galeria = self.store.gallery(self.model_id)
        if not galeria:
            return None, None, RAZAO_GALERIA_VAZIA

        candidatos: List[Tuple[str, float]] = []
        for user_id, vetores in galeria.items():
            melhor = min(
                _distancia_euclidiana(consulta, _l2_normalizar(v)) for v in vetores
            )
            candidatos.append((user_id, melhor))
        candidatos.sort(key=lambda par: par[1])

        melhor_id, melhor_dist = candidatos[0]
        if melhor_dist > self.threshold:
            return None, melhor_dist, RAZAO_DESCONHECIDO

        if len(candidatos) >= 2:
            _, segunda_dist = candidatos[1]
            if (segunda_dist - melhor_dist) < self.margin:
                return None, melhor_dist, RAZAO_AMBIGUO

        user = self.store.get_user(melhor_id)
        if user is None:
            # Inconsistência de dados: trata como desconhecido em vez de estourar.
            return None, melhor_dist, RAZAO_DESCONHECIDO
        return user, melhor_dist, "identificado"

    def attempt(
        self,
        vector: Optional[Sequence[float]],
        area: str,
        source: str,
        failure: Optional[str] = None,
        simulated: bool = False,
    ) -> Decision:
        if area not in AREAS:
            raise ErroDominio(f"Área desconhecida: {area!r}")
        if source not in FONTES_VALIDAS:
            raise ErroDominio(f"Origem inválida: {source!r}")

        if failure is not None:
            decisao = Decision(
                user_id=None,
                user_name=ID_DESCONHECIDO,
                user_level=None,
                area=area,
                granted=False,
                reason=failure,
                distance=None,
            )
        else:
            user, distancia, motivo = self.identify(vector)
            if user is None:
                decisao = Decision(
                    user_id=None,
                    user_name=ID_DESCONHECIDO,
                    user_level=None,
                    area=area,
                    granted=False,
                    reason=motivo,
                    distance=distancia,
                )
            else:
                autorizado = is_authorized(user, area)
                decisao = Decision(
                    user_id=user.id,
                    user_name=user.name,
                    user_level=user.level,
                    area=area,
                    granted=autorizado,
                    reason=RAZAO_AUTORIZADO if autorizado else RAZAO_SEM_NIVEL,
                    distance=distancia,
                )

        # Se a auditoria falhar, a exceção se propaga e nenhuma autorização
        # bem-sucedida é retornada ao chamador.
        self.store.log(decisao, source=source, simulated=simulated)
        return decisao
