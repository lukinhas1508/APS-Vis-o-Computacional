#!/usr/bin/env python3
"""cofre.py — CLI do Cofre Acadêmico com Reconhecimento Facial (protótipo).

Protótipo acadêmico local. Nenhuma fechadura física é acionada, nenhum
sistema governamental real é acessado e nenhum documento real do Ministério
do Meio Ambiente é utilizado. Todas as liberações são simuladas.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import core

BANCO_PADRAO = "data/cofre.sqlite3"


# ---------------------------------------------------------------------------
# Utilitários de saída
# ---------------------------------------------------------------------------

def _decisao_para_dict(decisao: core.Decision) -> dict:
    return {
        "user_id": decisao.user_id,
        "user_name": decisao.user_name,
        "user_level": decisao.user_level,
        "area": decisao.area,
        "granted": decisao.granted,
        "reason": decisao.reason,
        "distance": decisao.distance,
    }


def _erro(msg: str) -> int:
    print(f"Erro: {msg}", file=sys.stderr)
    return 2


# ---------------------------------------------------------------------------
# Subcomandos
# ---------------------------------------------------------------------------

def cmd_diagnostico(args: argparse.Namespace) -> int:
    """Mostra versão do Python, versões de dependências e integridade dos pesos.

    Este comando NÃO testa câmera nem inferência real.
    """
    import platform

    print(f"Python: {platform.python_version()} ({platform.architecture()[0]})")

    dependencias = [
        "tensorflow", "keras", "keras_facenet", "numpy", "scipy",
        "cv2", "mtcnn", "sklearn", "matplotlib",
    ]
    for nome in dependencias:
        try:
            modulo = __import__(nome)
            versao = getattr(modulo, "__version__", "desconhecida")
            print(f"  {nome}: {versao}")
        except Exception as exc:  # noqa: BLE001 - diagnóstico tolerante
            print(f"  {nome}: NÃO DISPONÍVEL ({exc.__class__.__name__})")

    try:
        import vision
        ok = vision.pesos_locais_validos("models")
        print(f"Pesos do modelo ({vision.MODEL_ID}): {'íntegros' if ok else 'ausentes ou inválidos'}")
    except Exception as exc:  # noqa: BLE001
        print(f"Pesos do modelo: não foi possível verificar ({exc})")

    print("\nObservação: este comando não testa câmera nem executa inferência.")
    return 0


def cmd_preparar_modelo(args: argparse.Namespace) -> int:
    import vision

    try:
        caminho = vision.preparar_modelo("models", allow_download=True)
        print(f"Pesos disponíveis e íntegros em: {caminho}")
        return 0
    except vision.ModelError as exc:
        return _erro(str(exc))


def cmd_simular(args: argparse.Namespace) -> int:
    import demo_sintetico

    saida = demo_sintetico.executar(args.saida)
    print(f"Demonstração sintética concluída. Artefatos em: {saida}")
    return 0


def cmd_gui(args: argparse.Namespace) -> int:
    import gui

    gui.launch(args.banco, threshold=args.limiar, margin=args.margem, camera=args.camera)
    return 0


def cmd_cadastrar(args: argparse.Namespace) -> int:
    import vision

    MIN_AMOSTRAS = 3
    if not args.consentimento:
        return _erro("consentimento explícito é obrigatório (--consentimento)")
    if len(args.imagens) < MIN_AMOSTRAS:
        return _erro(f"são necessárias pelo menos {MIN_AMOSTRAS} imagens distintas")

    pipeline = vision.FacePipeline(allow_download=False)
    embeddings = []
    for caminho in args.imagens:
        try:
            imagem = vision.load_image(caminho)
            amostra = pipeline.extract(imagem)
        except vision.FaceError as exc:
            return _erro(f"falha ao processar {caminho!r}: {exc}")
        except vision.ModelError as exc:
            return _erro(str(exc))
        embeddings.append(amostra.embedding)

    store = core.Store(args.banco)
    try:
        store.enroll(
            user_id=args.id,
            name=args.nome,
            level=args.nivel,
            division=args.divisao or "",
            consentimento=True,
            model_id=vision.MODEL_ID,
            embeddings=embeddings,
        )
    except core.ErroDominio as exc:
        return _erro(str(exc))
    finally:
        store.close()

    print(f"Usuário {args.id!r} cadastrado com {len(embeddings)} amostras.")
    return 0


def cmd_verificar(args: argparse.Namespace) -> int:
    import vision

    if args.area not in core.AREAS:
        return _erro(f"área inválida: {args.area!r}")

    pipeline = vision.FacePipeline(allow_download=False)
    store = core.Store(args.banco)
    try:
        servico = core.AccessService(store, vision.MODEL_ID, threshold=args.limiar, margin=args.margem)
        falha = None
        embedding = None
        try:
            imagem = vision.load_image(args.imagem)
            amostra = pipeline.extract(imagem)
            embedding = amostra.embedding
        except vision.FaceError as exc:
            falha = exc.reason

        decisao = servico.attempt(embedding, args.area, source="imagem", failure=falha, simulated=False)
    finally:
        store.close()

    print(json.dumps(_decisao_para_dict(decisao), ensure_ascii=False, indent=2))
    return 0 if decisao.granted else 1


def cmd_webcam(args: argparse.Namespace) -> int:
    import cv2

    import vision

    if args.area not in core.AREAS:
        return _erro(f"área inválida: {args.area!r}")

    pipeline = vision.FacePipeline(allow_download=False)
    store = core.Store(args.banco)
    try:
        servico = core.AccessService(store, vision.MODEL_ID, threshold=args.limiar, margin=args.margem)
        try:
            with vision.Webcam(args.camera) as cam:
                while True:
                    quadro = cam.read()
                    if quadro is None:
                        break
                    falha = None
                    embedding = None
                    try:
                        amostra = pipeline.extract(quadro)
                        embedding = amostra.embedding
                    except vision.FaceError as exc:
                        falha = exc.reason

                    decisao = servico.attempt(
                        embedding, args.area, source="webcam", failure=falha, simulated=False
                    )
                    print(json.dumps(_decisao_para_dict(decisao), ensure_ascii=False))

                    cv2.imshow("Cofre — pressione Q ou Esc para sair", quadro)
                    tecla = cv2.waitKey(1) & 0xFF
                    if tecla in (ord("q"), ord("Q"), 27):
                        break
        except KeyboardInterrupt:
            print("Interrompido pelo teclado. Nenhuma liberação física foi acionada.")
        finally:
            cv2.destroyAllWindows()
    finally:
        store.close()
    return 0


def cmd_exportar(args: argparse.Namespace) -> int:
    store = core.Store(args.banco)
    try:
        store.export(args.destino)
    except core.ErroDominio as exc:
        return _erro(str(exc))
    finally:
        store.close()
    print(f"Exportado para {args.destino}")
    return 0


def cmd_avaliar(args: argparse.Namespace) -> int:
    import evaluation

    try:
        saida = evaluation.evaluate(
            args.manifesto, args.saida, args.banco, threshold=args.limiar, margin=args.margem
        )
    except core.ErroDominio as exc:
        return _erro(str(exc))
    print(f"Avaliação concluída. Resultados em: {saida}")
    return 0


# ---------------------------------------------------------------------------
# Construção do parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cofre",
        description=(
            "Cofre acadêmico com reconhecimento facial (protótipo local, simulado). "
            "Não aciona fechaduras físicas nem acessa sistemas governamentais reais."
        ),
    )
    parser.add_argument("--banco", default=BANCO_PADRAO, help=f"Caminho do banco SQLite (padrão: {BANCO_PADRAO})")
    parser.add_argument("--limiar", type=float, default=0.8, help="Limiar de distância (padrão: 0.8)")
    parser.add_argument("--margem", type=float, default=0.1, help="Margem mínima entre identidades (padrão: 0.1)")

    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("diagnostico", help="Mostra versões e integridade dos pesos (não testa câmera/inferência)")
    p.set_defaults(func=cmd_diagnostico)

    p = sub.add_parser("preparar-modelo", help="Baixa e valida os pesos pré-treinados")
    p.set_defaults(func=cmd_preparar_modelo)

    p = sub.add_parser("simular", help="Executa a demonstração sintética (não usa TensorFlow/OpenCV)")
    p.add_argument("--saida", default=None, help="Pasta de saída (padrão: reports/simulacao_<timestamp>)")
    p.set_defaults(func=cmd_simular)

    p = sub.add_parser("gui", help="Abre a interface gráfica Tkinter")
    p.add_argument("--camera", type=int, default=0, help="Índice da câmera (padrão: 0)")
    p.set_defaults(func=cmd_gui)

    p = sub.add_parser("cadastrar", help="Cadastra um novo usuário a partir de imagens")
    p.add_argument("--id", required=True, dest="id")
    p.add_argument("--nome", required=True)
    p.add_argument("--nivel", type=int, required=True, choices=(1, 2, 3))
    p.add_argument("--divisao", default="", choices=("", "Toxinas", "Fiscalização"))
    p.add_argument("--consentimento", action="store_true")
    p.add_argument("imagens", nargs="+", help="Caminhos das imagens (mínimo 3)")
    p.set_defaults(func=cmd_cadastrar)

    p = sub.add_parser("verificar", help="Verifica uma imagem contra a galeria e retorna a decisão em JSON")
    p.add_argument("imagem")
    p.add_argument("--area", required=True, choices=list(core.AREAS.keys()))
    p.set_defaults(func=cmd_verificar)

    p = sub.add_parser("webcam", help="Verifica continuamente via webcam (Q ou Esc encerra)")
    p.add_argument("--area", required=True, choices=list(core.AREAS.keys()))
    p.add_argument("--camera", type=int, default=0)
    p.set_defaults(func=cmd_webcam)

    p = sub.add_parser("exportar", help="Exporta as tentativas registradas para um CSV")
    p.add_argument("destino")
    p.set_defaults(func=cmd_exportar)

    p = sub.add_parser("avaliar", help="Avalia o desempenho a partir de um manifesto rotulado")
    p.add_argument("manifesto")
    p.add_argument("--saida", required=True)
    p.set_defaults(func=cmd_avaliar)

    return parser


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nInterrompido pelo teclado. Nenhuma liberação física foi acionada.", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - mensagens de erro claras na CLI
        return _erro(str(exc))


if __name__ == "__main__":
    raise SystemExit(main())
