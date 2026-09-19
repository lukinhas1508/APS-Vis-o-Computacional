"""gui.py — Interface gráfica Tkinter do Cofre Acadêmico (protótipo).

PROTÓTIPO ACADÊMICO: não há prova de vida, nenhuma fechadura física é
acionada e não há login administrativo — o cadastro pressupõe um operador
local confiável, presente fisicamente junto ao equipamento.

Concorrência: uma única thread de inferência processa os quadros; o SQLite
(via core.Store) só é acessado pela thread principal (interface). A thread de
inferência devolve resultados por meio de uma fila (queue) consumida
periodicamente pela interface.
"""
from __future__ import annotations

import base64
import queue
import threading
import time
import tkinter as tk
from hashlib import sha256
from tkinter import filedialog, messagebox, ttk
from typing import Optional

import core

AVISO_PROTOTIPO = (
    "PROTÓTIPO ACADÊMICO — sem prova de vida. Reconhecimento facial simulado; "
    "nenhuma fechadura física é acionada e nenhum sistema governamental real é acessado."
)

INTERVALO_VERIFICACAO_S = 2.0
IDADE_MAXIMA_QUADRO_WEBCAM_S = 2.0
INTERVALO_MIN_COLETA_S = 1.0
MAX_AMOSTRAS_TEMP = 10
MIN_AMOSTRAS_CADASTRO = 3

TEXTO_PERMITIDO = "PERMITIDO — SOMENTE SIMULAÇÃO"
TEXTO_NEGADO = "NEGADO"
TEXTO_SEM_AUTORIZACAO = "SEM AUTORIZAÇÃO"


class _Trabalho:
    """Unidade de trabalho enviada à thread de inferência."""

    def __init__(self, tipo: str, imagem=None, geracao: int = 0, timestamp: float = 0.0):
        self.tipo = tipo  # "webcam" ou "imagem"
        self.imagem = imagem
        self.geracao = geracao
        self.timestamp = timestamp


class _ThreadInferencia(threading.Thread):
    """Única thread de inferência: consome trabalhos e produz resultados.

    Não acessa o SQLite diretamente — apenas o pipeline de visão computacional
    (vision.FacePipeline), que é independente de I/O de banco de dados.
    """

    def __init__(self, fila_trabalho: "queue.Queue[Optional[_Trabalho]]", fila_resultado: "queue.Queue"):
        super().__init__(daemon=True)
        self.fila_trabalho = fila_trabalho
        self.fila_resultado = fila_resultado
        self._pipeline = None

    def _garantir_pipeline(self):
        if self._pipeline is None:
            import vision
            self._pipeline = vision.FacePipeline(allow_download=False)
        return self._pipeline

    def run(self) -> None:
        import vision

        while True:
            trabalho = self.fila_trabalho.get()
            if trabalho is None:
                return
            embedding = None
            falha = None
            try:
                pipeline = self._garantir_pipeline()
                amostra = pipeline.extract(trabalho.imagem)
                embedding = amostra.embedding
            except vision.FaceError as exc:
                falha = exc.reason
            except vision.ModelError as exc:
                falha = str(exc)
            except Exception as exc:  # noqa: BLE001 - nunca deixa a thread morrer
                falha = f"erro_interno:{exc}"
            self.fila_resultado.put(
                {
                    "tipo": trabalho.tipo,
                    "geracao": trabalho.geracao,
                    "timestamp": trabalho.timestamp,
                    "embedding": embedding,
                    "falha": falha,
                }
            )


class CofreGUI:
    def __init__(self, root: tk.Tk, database: str, threshold: float, margin: float, camera: int):
        self.root = root
        self.root.title("Cofre Acadêmico — Controle de Acesso por Reconhecimento Facial (Simulado)")
        self.root.geometry("1120x850")

        self.database_path = database
        self.store = core.Store(database)

        # Modelo é resolvido de forma tardia (depende de vision.MODEL_ID, que
        # exige importar vision — feito só quando necessário).
        self._model_id: Optional[str] = None
        self.access_service: Optional[core.AccessService] = None
        self.threshold = threshold
        self.margin = margin

        self.camera_index = camera
        self._webcam = None
        self._webcam_ativa = False

        self._fila_trabalho: "queue.Queue[Optional[_Trabalho]]" = queue.Queue()
        self._fila_resultado: "queue.Queue" = queue.Queue()
        self._thread_inferencia = _ThreadInferencia(self._fila_trabalho, self._fila_resultado)
        self._thread_inferencia.start()

        # Geração: incrementada sempre que área/fonte/cadastro mudam, para
        # descartar resultados obsoletos que cheguem depois da mudança.
        self._geracao_atual = 0
        self._ultima_verificacao_ts = 0.0
        self._ultimo_resultado_permitido_ts: Optional[float] = None

        self._amostras_temporarias: list[bytes] = []  # PNGs crus para hash/duplicidade
        self._amostras_temporarias_embeddings: list[list[float]] = []
        self._ultima_coleta_ts = 0.0
        self._coletando = False

        self._quadro_atual = None
        self._imagem_importada = None

        self._construir_interface()
        self.root.protocol("WM_DELETE_WINDOW", self._ao_fechar)
        self._agendar_poll_resultados()

    # ------------------------------------------------------------------
    # Construção da interface
    # ------------------------------------------------------------------

    def _construir_interface(self) -> None:
        aviso = tk.Label(
            self.root, text=AVISO_PROTOTIPO, fg="white", bg="#7a1f1f",
            wraplength=1080, justify="left", padx=10, pady=6, font=("TkDefaultFont", 10, "bold"),
        )
        aviso.pack(fill="x", side="top")

        corpo = tk.Frame(self.root)
        corpo.pack(fill="both", expand=True)

        esquerda = tk.Frame(corpo, padx=10, pady=10)
        esquerda.pack(side="left", fill="both", expand=True)

        direita = tk.Frame(corpo, padx=10, pady=10, width=340)
        direita.pack(side="right", fill="y")

        # ---- Esquerda: verificação de acesso ----
        tk.Label(esquerda, text="Área", font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        self.combo_area = ttk.Combobox(
            esquerda, values=list(core.AREAS.keys()), state="readonly"
        )
        self.combo_area.current(0)
        self.combo_area.bind("<<ComboboxSelected>>", lambda e: self._invalidar_geracao())
        self.combo_area.pack(anchor="w", pady=(0, 8))

        self.canvas_video = tk.Label(esquerda, bg="black", width=70, height=20)
        self.canvas_video.pack(fill="both", expand=True, pady=(0, 8))

        self.label_decisao = tk.Label(
            esquerda, text="—", font=("TkDefaultFont", 16, "bold"), fg="#333333"
        )
        self.label_decisao.pack(anchor="w")

        self.label_mensagem = tk.Label(esquerda, text="", fg="#555555", wraplength=700, justify="left")
        self.label_mensagem.pack(anchor="w", pady=(0, 8))

        botoes = tk.Frame(esquerda)
        botoes.pack(anchor="w", pady=(0, 8))
        tk.Button(botoes, text="Importar imagem", command=self._importar_imagem).pack(side="left", padx=2)
        tk.Button(botoes, text="Verificar", command=self._verificar_imagem_importada).pack(side="left", padx=2)
        tk.Button(botoes, text="Iniciar câmera", command=self._iniciar_camera).pack(side="left", padx=2)
        tk.Button(botoes, text="Parar", command=self._parar_camera).pack(side="left", padx=2)
        tk.Button(botoes, text="Exportar CSV", command=self._exportar_csv).pack(side="left", padx=2)

        tk.Label(esquerda, text="Histórico de tentativas", font=("TkDefaultFont", 10, "bold")).pack(
            anchor="w", pady=(8, 0)
        )
        self.lista_historico = tk.Listbox(esquerda, height=8)
        self.lista_historico.pack(fill="both", expand=False)

        # ---- Direita: cadastro administrativo local ----
        tk.Label(direita, text="Cadastro administrativo local", font=("TkDefaultFont", 11, "bold")).pack(
            anchor="w"
        )
        tk.Label(
            direita,
            text="Não há login administrativo: pressupõe-se operador local confiável, "
                 "fisicamente presente junto ao equipamento.",
            wraplength=320, fg="#555555", justify="left",
        ).pack(anchor="w", pady=(0, 8))

        tk.Label(direita, text="ID").pack(anchor="w")
        self.entry_id = tk.Entry(direita)
        self.entry_id.pack(fill="x")

        tk.Label(direita, text="Nome").pack(anchor="w")
        self.entry_nome = tk.Entry(direita)
        self.entry_nome.pack(fill="x")

        tk.Label(direita, text="Nível").pack(anchor="w")
        self.combo_nivel = ttk.Combobox(direita, values=["1", "2", "3"], state="readonly")
        self.combo_nivel.current(0)
        self.combo_nivel.pack(fill="x")

        tk.Label(direita, text="Divisão (obrigatória p/ nível 2)").pack(anchor="w")
        self.combo_divisao = ttk.Combobox(
            direita, values=["", "Toxinas", "Fiscalização"], state="readonly"
        )
        self.combo_divisao.current(0)
        self.combo_divisao.pack(fill="x")

        for widget in (self.entry_id, self.entry_nome):
            widget.bind("<KeyRelease>", lambda e: self._limpar_coleta_temporaria())
        self.combo_nivel.bind("<<ComboboxSelected>>", lambda e: self._limpar_coleta_temporaria())
        self.combo_divisao.bind("<<ComboboxSelected>>", lambda e: self._limpar_coleta_temporaria())

        self.var_consentimento = tk.BooleanVar(value=False)
        tk.Checkbutton(
            direita, text="Consentimento explícito do titular obtido",
            variable=self.var_consentimento,
        ).pack(anchor="w", pady=(6, 6))

        tk.Button(direita, text="Coletar frame atual da webcam", command=self._coletar_frame_webcam).pack(
            fill="x", pady=2
        )
        tk.Button(direita, text="Limpar coleta temporária", command=self._limpar_coleta_temporaria).pack(
            fill="x", pady=2
        )
        self.label_coleta = tk.Label(direita, text="Amostras coletadas: 0")
        self.label_coleta.pack(anchor="w", pady=(2, 8))

        tk.Button(
            direita, text="Cadastrar com amostras coletadas", command=self._cadastrar_com_coletadas
        ).pack(fill="x", pady=2)

        tk.Label(
            direita,
            text="O operador deve garantir que todas as amostras são da mesma pessoa. "
                 "Diferenças entre as imagens NÃO constituem prova de vida.",
            wraplength=320, fg="#7a1f1f", justify="left",
        ).pack(anchor="w", pady=(8, 0))

    # ------------------------------------------------------------------
    # Estado / geração
    # ------------------------------------------------------------------

    def _invalidar_geracao(self) -> None:
        """Descarta resultados pendentes ao mudar área/fonte/cadastro."""
        self._geracao_atual += 1
        self._ultimo_resultado_permitido_ts = None
        self.label_decisao.config(text="—", fg="#333333")
        self.label_mensagem.config(text="")

    def _garantir_access_service(self):
        if self.access_service is None:
            import vision
            self._model_id = vision.MODEL_ID
            self.access_service = core.AccessService(
                self.store, self._model_id, threshold=self.threshold, margin=self.margin
            )
        return self.access_service

    # ------------------------------------------------------------------
    # Importar / verificar imagem
    # ------------------------------------------------------------------

    def _importar_imagem(self) -> None:
        import vision

        caminho = filedialog.askopenfilename(
            title="Selecionar imagem",
            filetypes=[("Imagens", "*.png *.jpg *.jpeg *.bmp"), ("Todos os arquivos", "*.*")],
        )
        if not caminho:
            return
        try:
            self._imagem_importada = vision.load_image(caminho)
        except vision.FaceError as exc:
            messagebox.showerror("Erro ao importar imagem", str(exc))
            return
        self._mostrar_quadro(self._imagem_importada)
        self._invalidar_geracao()

    def _verificar_imagem_importada(self) -> None:
        if self._imagem_importada is None:
            messagebox.showinfo("Verificar", "Importe uma imagem primeiro.")
            return
        geracao = self._geracao_atual
        trabalho = _Trabalho(tipo="imagem", imagem=self._imagem_importada, geracao=geracao, timestamp=time.monotonic())
        self._fila_trabalho.put(trabalho)

    # ------------------------------------------------------------------
    # Webcam
    # ------------------------------------------------------------------

    def _iniciar_camera(self) -> None:
        if self._webcam_ativa:
            return
        import vision

        try:
            self._webcam = vision.Webcam(self.camera_index)
            self._webcam.__enter__()
        except vision.FaceError as exc:
            messagebox.showerror("Câmera indisponível", str(exc))
            return
        self._webcam_ativa = True
        self._invalidar_geracao()
        self._loop_webcam()

    def _parar_camera(self) -> None:
        self._webcam_ativa = False
        if self._webcam is not None:
            self._webcam.close()
            self._webcam = None

    def _loop_webcam(self) -> None:
        if not self._webcam_ativa or self._webcam is None:
            return
        quadro = self._webcam.read()
        if quadro is not None:
            self._quadro_atual = quadro
            self._mostrar_quadro(quadro)

            agora = time.monotonic()
            if agora - self._ultima_verificacao_ts >= INTERVALO_VERIFICACAO_S:
                self._ultima_verificacao_ts = agora
                trabalho = _Trabalho(
                    tipo="webcam", imagem=quadro.copy(), geracao=self._geracao_atual, timestamp=agora
                )
                self._fila_trabalho.put(trabalho)

        self.root.after(30, self._loop_webcam)

    def _mostrar_quadro(self, quadro) -> None:
        import cv2

        ok, buffer = cv2.imencode(".png", quadro)
        if not ok:
            return
        b64 = base64.b64encode(buffer.tobytes())
        imagem_tk = tk.PhotoImage(data=b64)
        self.canvas_video.configure(image=imagem_tk)
        self.canvas_video.image = imagem_tk  # evita coleta de lixo prematura

    # ------------------------------------------------------------------
    # Consumo de resultados da thread de inferência
    # ------------------------------------------------------------------

    def _agendar_poll_resultados(self) -> None:
        try:
            while True:
                resultado = self._fila_resultado.get_nowait()
                self._processar_resultado(resultado)
        except queue.Empty:
            pass
        self.root.after(100, self._agendar_poll_resultados)

    def _processar_resultado(self, resultado: dict) -> None:
        if resultado["geracao"] != self._geracao_atual:
            return  # obsoleto: área/fonte/cadastro mudou nesse meio-tempo

        if resultado["tipo"] == "webcam":
            idade = time.monotonic() - resultado["timestamp"]
            if idade >= IDADE_MAXIMA_QUADRO_WEBCAM_S:
                return  # resultado de webcam expirado

        area = self.combo_area.get()
        fonte = "webcam" if resultado["tipo"] == "webcam" else "imagem"
        try:
            servico = self._garantir_access_service()
            decisao = servico.attempt(
                resultado["embedding"], area, source=fonte, failure=resultado["falha"], simulated=False
            )
        except core.ErroDominio as exc:
            self.label_mensagem.config(text=f"Erro: {exc}")
            return

        self._exibir_decisao(decisao)
        self._registrar_no_historico(decisao, fonte)

    def _exibir_decisao(self, decisao: core.Decision) -> None:
        agora = time.monotonic()
        if decisao.granted:
            self.label_decisao.config(text=TEXTO_PERMITIDO, fg="#1a7a1a")
            self._ultimo_resultado_permitido_ts = agora
        else:
            texto = TEXTO_NEGADO if decisao.reason not in (core.RAZAO_GALERIA_VAZIA,) else TEXTO_SEM_AUTORIZACAO
            self.label_decisao.config(text=texto, fg="#7a1f1f")

        detalhes = f"Motivo: {decisao.reason}"
        if decisao.distance is not None:
            detalhes += f" | distância: {decisao.distance:.4f}"
        if decisao.user_name:
            detalhes += f" | identificado: {decisao.user_name}"
        self.label_mensagem.config(text=detalhes)

        # Autorizações visuais expiram após o intervalo de verificação.
        self.root.after(int(INTERVALO_VERIFICACAO_S * 1000) + 200, self._expirar_autorizacao_se_necessario)

    def _expirar_autorizacao_se_necessario(self) -> None:
        if self._ultimo_resultado_permitido_ts is None:
            return
        if time.monotonic() - self._ultimo_resultado_permitido_ts >= INTERVALO_VERIFICACAO_S:
            self.label_decisao.config(text=TEXTO_SEM_AUTORIZACAO, fg="#7a1f1f")
            self._ultimo_resultado_permitido_ts = None

    def _registrar_no_historico(self, decisao: core.Decision, fonte: str) -> None:
        status = "PERMITIDO" if decisao.granted else "NEGADO"
        linha = f"[{fonte}] {decisao.user_name} @ {decisao.area}: {status} ({decisao.reason})"
        self.lista_historico.insert(0, linha)

    # ------------------------------------------------------------------
    # Cadastro
    # ------------------------------------------------------------------

    def _pausar_verificacao_automatica(self) -> None:
        self._coletando = True

    def _retomar_verificacao_automatica(self) -> None:
        self._coletando = False

    def _coletar_frame_webcam(self) -> None:
        if self._quadro_atual is None:
            messagebox.showinfo("Coletar", "Inicie a câmera e aguarde um quadro antes de coletar.")
            return
        agora = time.monotonic()
        if agora - self._ultima_coleta_ts < INTERVALO_MIN_COLETA_S:
            messagebox.showinfo("Coletar", "Aguarde ao menos 1 segundo entre coletas.")
            return
        if len(self._amostras_temporarias) >= MAX_AMOSTRAS_TEMP:
            messagebox.showinfo("Coletar", f"Limite de {MAX_AMOSTRAS_TEMP} amostras temporárias atingido.")
            return

        self._pausar_verificacao_automatica()
        self._processar_amostra_para_cadastro(self._quadro_atual.copy())
        self._ultima_coleta_ts = agora

    def _processar_amostra_para_cadastro(self, imagem) -> None:
        import cv2
        import vision

        try:
            pipeline = vision.FacePipeline(allow_download=False)
            amostra = pipeline.extract(imagem)
        except vision.FaceError as exc:
            messagebox.showerror("Falha ao processar amostra", str(exc))
            return

        ok, buffer = cv2.imencode(".png", imagem)
        if not ok:
            messagebox.showerror("Falha ao processar amostra", "Não foi possível codificar a imagem.")
            return
        pixels_hash = sha256(imagem.tobytes()).hexdigest()
        for h in getattr(self, "_hashes_coletados", []):
            if h == pixels_hash:
                messagebox.showinfo("Amostra duplicada", "Esta imagem (mesmos pixels) já foi coletada.")
                return
        if not hasattr(self, "_hashes_coletados"):
            self._hashes_coletados = []
        self._hashes_coletados.append(pixels_hash)

        self._amostras_temporarias.append(buffer.tobytes())
        self._amostras_temporarias_embeddings.append(amostra.embedding)
        self.label_coleta.config(text=f"Amostras coletadas: {len(self._amostras_temporarias)}")

    def _limpar_coleta_temporaria(self) -> None:
        self._amostras_temporarias.clear()
        self._amostras_temporarias_embeddings.clear()
        self._hashes_coletados = []
        self.label_coleta.config(text="Amostras coletadas: 0")
        self._retomar_verificacao_automatica()

    def _cadastrar_com_coletadas(self) -> None:
        import vision

        if len(self._amostras_temporarias_embeddings) < MIN_AMOSTRAS_CADASTRO:
            messagebox.showinfo(
                "Cadastrar",
                f"São necessárias pelo menos {MIN_AMOSTRAS_CADASTRO} amostras distintas da mesma pessoa.",
            )
            return
        if not self.var_consentimento.get():
            messagebox.showinfo("Cadastrar", "É necessário marcar o consentimento explícito do titular.")
            return

        try:
            self.store.enroll(
                user_id=self.entry_id.get(),
                name=self.entry_nome.get(),
                level=int(self.combo_nivel.get()),
                division=self.combo_divisao.get(),
                consentimento=True,
                model_id=vision.MODEL_ID,
                embeddings=self._amostras_temporarias_embeddings,
            )
        except core.ErroDominio as exc:
            messagebox.showerror("Falha no cadastro", str(exc))
            return

        messagebox.showinfo("Cadastrar", "Cadastro realizado com sucesso.")
        self._limpar_coleta_temporaria()
        self.var_consentimento.set(False)

    # ------------------------------------------------------------------
    # Exportação e encerramento
    # ------------------------------------------------------------------

    def _exportar_csv(self) -> None:
        destino = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not destino:
            return
        try:
            self.store.export(destino)
        except core.ErroDominio as exc:
            messagebox.showerror("Falha ao exportar", str(exc))
            return
        messagebox.showinfo("Exportar", f"Exportado para {destino}")

    def _ao_fechar(self) -> None:
        self._parar_camera()
        self._fila_trabalho.put(None)
        self.store.close()
        self.root.destroy()


def launch(database: str, threshold: float = 0.8, margin: float = 0.1, camera: int = 0) -> None:
    root = tk.Tk()
    CofreGUI(root, database=database, threshold=threshold, margin=margin, camera=camera)
    root.mainloop()


if __name__ == "__main__":
    launch("data/cofre.sqlite3")
