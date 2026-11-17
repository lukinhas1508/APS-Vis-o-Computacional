# Cofre Acadêmico — Modo de Uso

Sistema de controle de acesso por reconhecimento facial para o cofre do Ministério do Meio Ambiente (protótipo acadêmico).

---

## 1. Como abrir

1. Baixe o arquivo `cofre-academico.html`
2. Abra-o diretamente no navegador (Chrome, Edge ou Firefox)
3. Ao abrir, o navegador pedirá permissão para acessar a câmera — clique em **Permitir**
4. A câmera ligará automaticamente
5. É necessária conexão com a internet (o detector facial MediaPipe é carregado de CDN)

> **Importante:** o arquivo deve ser aberto diretamente no navegador, não dentro de iframes ou visualizadores embutidos.

---

## 2. Cadastrar um usuário

Antes de verificar acessos, é preciso cadastrar pelo menos um usuário.

1. Clique na aba **Cadastrar** no canto superior direito
2. Preencha os campos:
   - **ID do usuário** — identificador único (ex: `ana.souza`)
   - **Nome completo** — nome da pessoa (ex: `Ana Souza`)
   - **Nível de acesso**:
     - **Nível 1 (Básico)** — acesso apenas à consulta geral
     - **Nível 2 (Diretor)** — acesso à consulta geral + registros da própria divisão
     - **Nível 3 (Ministro)** — acesso a todas as áreas (apenas um permitido)
   - **Divisão** (apenas para nível 2): Toxinas ou Fiscalização
3. Marque a caixa de **consentimento**
4. Conclua a **prova de vida** (seção 3) — o botão de coleta só é liberado depois disso
5. Colete pelo menos **3 amostras faciais**:
   - Clique em **Coletar frame da webcam** (só o recorte do rosto é usado)
   - Repita pelo menos 3 vezes (a barra de progresso indica o andamento)
   - Varie levemente a posição do rosto entre as coletas para melhor precisão
   - Se o rosto sair do quadro, a sessão de vida termina e a coleta recomeça
6. Clique em **Cadastrar usuário**

> Após esta atualização, cadastros antigos são apagados automaticamente
> (o formato do embedding mudou) — recadastre os usuários.

Os usuários cadastrados aparecem na lista abaixo do formulário.

---

## 3. Prova de vida (obrigatória)

Só passa quem está **realmente vivo e presente na frente da câmera**. Fotos
impressas, fotos na tela do celular e imagens paradas são bloqueadas.

1. Com a câmera ligada, olhe de frente para ela.
2. Siga as instruções que aparecem sobre o vídeo — são **3 desafios
   sorteados** a cada vez, sempre incluindo **piscar**, mais dois entre:
   **virar o rosto para a sua esquerda**, **virar para a sua direita** e
   **abrir a boca**. Depois de cada movimento, volte a olhar de frente.
3. Ao concluir, o selo no canto do vídeo fica verde (**Vivo**). A aprovação
   vale por 20 segundos **enquanto o mesmo rosto continuar no quadro**.

O desafio recomeça se: o rosto sair do quadro, aparecer um segundo rosto,
houver troca brusca de rosto, o tempo de uma etapa (8 s) acabar ou você
virar para o lado errado.

> Por que uma foto não passa: uma foto não pisca nem abre a boca, e
> inclinar/balançar o celular não reproduz o giro 3D da cabeça — o sistema
> mede a posição da ponta do nariz em relação aos cantos dos olhos, que só
> muda quando uma cabeça real gira.

> O detector facial (MediaPipe) é carregado da internet na abertura da
> página. Sem ele, **todos os acessos são negados** (falha fechada).

---

## 4. Verificar acesso

1. Clique na aba **Verificar**
2. Selecione a **área** que deseja acessar:
   - **Consulta geral** — nível 1 (qualquer usuário)
   - **Registros de toxinas** — nível 2 (diretores da divisão Toxinas + ministro)
   - **Registros de fiscalização** — nível 2 (diretores da divisão Fiscalização + ministro)
   - **Gabinete ministerial** — nível 3 (apenas ministro)
3. Conclua a prova de vida (seção 3)
4. Clique em **Verificar agora** ou aguarde a verificação automática (a cada 2,5 segundos,
   apenas enquanto a prova de vida estiver aprovada)
5. O resultado aparece no banner inferior:
   - **Verde (ACESSO PERMITIDO)** — usuário identificado e autorizado para a área
   - **Vermelho (ACESSO NEGADO)** — usuário não identificado, sem permissão ou sem prova de vida
     (`prova_de_vida_pendente`, `prova_de_vida_expirada`, `rosto_ausente`, `detector_facial_indisponivel`)

---

## 5. Histórico

Clique na aba **Histórico** para ver o registro completo de todas as tentativas de acesso, com horário, nome, área e resultado.

---

## 6. Regras de autorização

| Área                     | Nível 1 | Nível 2 (Toxinas) | Nível 2 (Fiscalização) | Nível 3 (Ministro) |
|--------------------------|---------|-------------------|------------------------|---------------------|
| Consulta geral           | ✅      | ✅                | ✅                     | ✅                  |
| Registros de toxinas     | ❌      | ✅                | ❌                     | ✅                  |
| Registros de fiscalização| ❌      | ❌                | ✅                     | ✅                  |
| Gabinete ministerial     | ❌      | ❌                | ❌                     | ✅                  |

---

## 7. Limitações do protótipo

- **Pseudo-embeddings** — o reconhecimento facial usa vetores simplificados (HOG + LBP + cor) extraídos do recorte do rosto (não usa FaceNet real no navegador)
- **Prova de vida ativa** — bloqueia fotos e imagens paradas; **não** cobre ataques avançados como vídeo/deepfake em tempo real controlado por um atacante ou máscaras 3D
- **Persistência local** — os dados ficam no IndexedDB do navegador (cifrados com AES-256-GCM)
- **Somente simulação** — o banner "ACESSO PERMITIDO" inclui o aviso "SOMENTE SIMULAÇÃO"

---

## 8. Requisitos

- Navegador moderno (Chrome 80+, Firefox 78+, Edge 80+)
- Câmera/webcam funcional
- Permissão de câmera concedida ao navegador
- Conexão com a internet (MediaPipe via CDN)
