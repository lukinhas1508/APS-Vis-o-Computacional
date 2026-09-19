"""demo_sintetico.py — Demonstração sintética (seção 12 da especificação).

Usa vetores ARTIFICIAIS de 4 dimensões, sob o identificador de modelo
SINTETICO-4D-NAO-FACIAL. Nenhuma imagem, câmera ou rede neural é usada aqui —
este módulo depende apenas de core.py (biblioteca padrão), para funcionar sem
TensorFlow/OpenCV.

As falhas de aquisição (múltiplos rostos, desfoque, câmera indisponível) são
INJETADAS propositalmente para exercitar o fluxo de negação. Os resultados
NÃO devem ser interpretados como acurácia de reconhecimento facial real.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import core

MODELO_SINTETICO = "SINTETICO-4D-NAO-FACIAL"


def _variacoes(base: List[float]) -> List[List[float]]:
    """Gera 3 vetores com pequenas variações artificiais em torno de `base`."""
    deslocamentos = (0.03, -0.02, 0.01)
    idx_vizinha = (base.index(max(base)) + 1) % len(base)
    variados = []
    for d in deslocamentos:
        vetor = list(base)
        vetor[idx_vizinha] = vetor[idx_vizinha] + d
        variados.append(vetor)
    return variados


def executar(saida: Optional["str | Path"] = None) -> Path:
    """Executa os nove casos da demonstração sintética e grava os artefatos.

    Gera, na pasta de saída: simulacao.sqlite3, tentativas.csv e resumo.json.
    Retorna o caminho da pasta de saída.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    pasta = Path(saida) if saida else Path("reports") / f"simulacao_{timestamp}"
    pasta.mkdir(parents=True, exist_ok=True)

    banco = pasta / "simulacao.sqlite3"
    store = core.Store(banco)
    try:
        usuarios = {
            "basico": (1, "", [1.0, 0.0, 0.0, 0.0]),
            "diretor": (2, "Toxinas", [0.0, 1.0, 0.0, 0.0]),
            "ministro": (3, "", [0.0, 0.0, 1.0, 0.0]),
        }
        amostras_query = {}
        for user_id, (nivel, divisao, base) in usuarios.items():
            variados = _variacoes(base)
            store.enroll(
                user_id=user_id,
                name=user_id.capitalize(),
                level=nivel,
                division=divisao,
                consentimento=True,
                model_id=MODELO_SINTETICO,
                embeddings=variados,
            )
            amostras_query[user_id] = variados[0]

        servico = core.AccessService(store, MODELO_SINTETICO, threshold=0.8, margin=0.1)

        # (identidade_para_consulta, área, motivo_de_falha_injetado)
        casos = [
            ("basico", "geral", None),
            ("basico", "ministerial", None),
            ("diretor", "toxinas", None),
            ("diretor", "fiscalizacao", None),
            ("ministro", "ministerial", None),
            ("desconhecido", "geral", None),
            (None, "geral", core.RAZAO_MULTIPLOS_ROSTOS),
            (None, "geral", core.RAZAO_IMAGEM_DESFOCADA),
            (None, "geral", core.RAZAO_CAMERA_INDISPONIVEL),
        ]

        decisoes = []
        for identidade, area, falha in casos:
            if falha is not None:
                vetor = None
            elif identidade == "desconhecido":
                vetor = [0.0, 0.0, 0.0, 1.0]
            else:
                vetor = amostras_query[identidade]
            decisao = servico.attempt(vetor, area, source="simulacao", failure=falha, simulated=True)
            decisoes.append(decisao)

        permitidas = sum(1 for d in decisoes if d.granted)
        negadas = len(decisoes) - permitidas

        caminho_csv = pasta / "tentativas.csv"
        store.export(caminho_csv)

        resumo = {
            "modelo": MODELO_SINTETICO,
            "total_tentativas": len(decisoes),
            "permitidas": permitidas,
            "negadas": negadas,
            "aviso": (
                "Demonstração SINTÉTICA. Os vetores são artificiais (não derivados de "
                "rostos reais) e as falhas de aquisição foram INJETADAS propositalmente "
                "para exercitar o fluxo de negação. Estes números NÃO representam "
                "acurácia de reconhecimento facial."
            ),
        }
        with (pasta / "resumo.json").open("w", encoding="utf-8") as f:
            json.dump(resumo, f, ensure_ascii=False, indent=2)
    finally:
        store.close()

    return pasta
