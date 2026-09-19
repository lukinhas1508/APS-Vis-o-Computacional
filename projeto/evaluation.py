"""evaluation.py — Avaliação de desempenho do reconhecimento facial.

Usa FacePipeline (vision.py) e AccessService.identify (core.py) sobre um
manifesto rotulado. NÃO registra essas execuções como tentativas de entrada
no banco (não chama Store.log / AccessService.attempt), pois são avaliações
offline, não acessos reais.

Protótipo acadêmico: limiar e margem padrão não estão calibrados para uso
real; não há detecção automática de vazamento entre conjuntos de cadastro,
validação e teste — isso é responsabilidade de quem organiza o manifesto.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Dict, List, Optional

import core


def _ler_manifesto(manifest_path: Path) -> List[Dict[str, str]]:
    if not manifest_path.is_file():
        raise core.ErroDominio(f"Manifesto não encontrado: {manifest_path}")

    with manifest_path.open("r", encoding="utf-8-sig", newline="") as f:
        leitor = csv.DictReader(f)
        if leitor.fieldnames != ["image", "user_id"]:
            raise core.ErroDominio(
                "Manifesto deve ter cabeçalho exatamente 'image,user_id'"
            )
        linhas = []
        for i, linha in enumerate(leitor, start=2):
            imagem = (linha.get("image") or "").strip()
            rotulo = (linha.get("user_id") or "").strip()
            if not imagem or not rotulo:
                raise core.ErroDominio(
                    f"Linha {i} do manifesto sem imagem ou rótulo válido"
                )
            linhas.append({"image": imagem, "user_id": rotulo})

    if not linhas:
        raise core.ErroDominio("Manifesto vazio")
    return linhas


def evaluate(
    manifest_path: "str | Path",
    output_dir: "str | Path",
    database: "str | Path",
    threshold: float = 0.8,
    margin: float = 0.1,
) -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from sklearn.metrics import classification_report, confusion_matrix

    import vision

    manifest_path = Path(manifest_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    linhas = _ler_manifesto(manifest_path)
    pasta_manifesto = manifest_path.parent

    store = core.Store(database)
    try:
        ids_cadastrados = {u.id for u in store.users()}
        for linha in linhas:
            rotulo = linha["user_id"]
            if rotulo != core.ID_DESCONHECIDO and rotulo not in ids_cadastrados:
                raise core.ErroDominio(
                    f"Rótulo {rotulo!r} do manifesto não corresponde a nenhum "
                    "usuário cadastrado na galeria do modelo"
                )

        pipeline = vision.FacePipeline(allow_download=False)
        acesso = core.AccessService(
            store, vision.MODEL_ID, threshold=threshold, margin=margin
        )

        registros = []
        falhas_por_tipo: Dict[str, int] = {}

        for linha in linhas:
            caminho_imagem = Path(linha["image"])
            if not caminho_imagem.is_absolute():
                caminho_imagem = pasta_manifesto / caminho_imagem

            predito: str
            distancia: Optional[float] = None
            erro: Optional[str] = None
            adquirida = True

            try:
                imagem = vision.load_image(caminho_imagem)
                amostra = pipeline.extract(imagem)
                usuario, distancia, _motivo = acesso.identify(amostra.embedding)
                predito = usuario.id if usuario is not None else core.ID_DESCONHECIDO
            except vision.FaceError as exc:
                adquirida = False
                erro = exc.reason
                predito = core.ID_DESCONHECIDO
                falhas_por_tipo[erro] = falhas_por_tipo.get(erro, 0) + 1

            registros.append(
                {
                    "image": linha["image"],
                    "user_id": linha["user_id"],
                    "predicted": predito,
                    "distance": distancia,
                    "erro": erro,
                    "adquirida": adquirida,
                }
            )
    finally:
        store.close()

    # ---------------- predictions.csv ----------------
    caminho_predicoes = output_dir / "predictions.csv"
    with caminho_predicoes.open("w", newline="", encoding="utf-8-sig") as f:
        escritor = csv.writer(f)
        escritor.writerow(["image", "user_id", "predicted", "distance", "erro"])
        for r in registros:
            escritor.writerow(
                [r["image"], r["user_id"], r["predicted"], r["distance"] or "", r["erro"] or ""]
            )

    # ---------------- métricas ----------------
    y_true = [r["user_id"] for r in registros]
    y_pred = [r["predicted"] for r in registros]
    rotulos = sorted(set(y_true) | set(y_pred))

    total = len(registros)
    acertos_geral = sum(1 for t, p in zip(y_true, y_pred) if t == p)
    acuracia_geral = acertos_geral / total if total else None

    adquiridas = [r for r in registros if r["adquirida"]]
    if adquiridas:
        acertos_adq = sum(1 for r in adquiridas if r["user_id"] == r["predicted"])
        acuracia_adquiridas = acertos_adq / len(adquiridas)
    else:
        acuracia_adquiridas = None

    relatorio = classification_report(
        y_true, y_pred, labels=rotulos, zero_division=0, output_dict=True
    )

    def _far_frr(registros_considerados):
        desconhecidos = [r for r in registros_considerados if r["user_id"] == core.ID_DESCONHECIDO]
        cadastrados = [r for r in registros_considerados if r["user_id"] != core.ID_DESCONHECIDO]
        far = (
            sum(1 for r in desconhecidos if r["predicted"] != core.ID_DESCONHECIDO) / len(desconhecidos)
            if desconhecidos
            else None
        )
        frr = (
            sum(1 for r in cadastrados if r["predicted"] == core.ID_DESCONHECIDO) / len(cadastrados)
            if cadastrados
            else None
        )
        return far, frr

    far_geral, frr_geral = _far_frr(registros)
    far_biometrica, frr_biometrica = _far_frr(adquiridas)

    confusoes_entre_cadastrados: Dict[str, int] = {}
    for r in registros:
        real, predito = r["user_id"], r["predicted"]
        if real != core.ID_DESCONHECIDO and predito != core.ID_DESCONHECIDO and real != predito:
            chave = f"{real}->{predito}"
            confusoes_entre_cadastrados[chave] = confusoes_entre_cadastrados.get(chave, 0) + 1

    metricas = {
        "total_amostras": total,
        "acuracia_geral": acuracia_geral,
        "acuracia_apenas_adquiridas": acuracia_adquiridas,
        "relatorio_classificacao": relatorio,
        "falhas_aquisicao": {
            "total": total - len(adquiridas),
            "tipos": falhas_por_tipo,
        },
        "far_geral": far_geral,
        "frr_geral": frr_geral,
        "far_biometrica": far_biometrica,
        "frr_biometrica": frr_biometrica,
        "confusoes_entre_cadastrados": confusoes_entre_cadastrados,
        "limiar": threshold,
        "margem": margin,
        "aviso": (
            "Protótipo acadêmico. Limiar e margem padrão não foram calibrados. "
            "Não há verificação automática de vazamento entre cadastro/validação/teste."
        ),
    }

    caminho_metricas = output_dir / "metrics.json"
    with caminho_metricas.open("w", encoding="utf-8") as f:
        json.dump(metricas, f, ensure_ascii=False, indent=2)

    # ---------------- confusion_matrix.png ----------------
    matriz = confusion_matrix(y_true, y_pred, labels=rotulos)
    fig, ax = plt.subplots(figsize=(max(6, len(rotulos)), max(5, len(rotulos))))
    im = ax.imshow(matriz, cmap="Blues")
    ax.set_xticks(range(len(rotulos)))
    ax.set_yticks(range(len(rotulos)))
    ax.set_xticklabels(rotulos, rotation=45, ha="right")
    ax.set_yticklabels(rotulos)
    ax.set_xlabel("Previsão")
    ax.set_ylabel("Identidade real")
    ax.set_title("Matriz de confusão — linhas: identidade real, colunas: previsão")
    for i in range(len(rotulos)):
        for j in range(len(rotulos)):
            ax.text(j, i, str(matriz[i, j]), ha="center", va="center", fontsize=8)
    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    caminho_matriz = output_dir / "confusion_matrix.png"
    fig.savefig(caminho_matriz)
    plt.close(fig)

    return output_dir
