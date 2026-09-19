# Cofre Acadêmico — Modo de Uso

Sistema de controle de acesso por reconhecimento facial para o cofre do Ministério do Meio Ambiente (protótipo acadêmico).

---

## 1. Como abrir

1. Baixe o arquivo `cofre-academico.html`
2. Abra-o diretamente no navegador (Chrome, Edge ou Firefox)
3. Ao abrir, o navegador pedirá permissão para acessar a câmera — clique em **Permitir**
4. A câmera ligará automaticamente

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
4. Colete pelo menos **3 amostras faciais**:
   - Posicione seu rosto na frente da câmera
   - Clique em **Coletar frame da webcam**
   - Repita pelo menos 3 vezes (a barra de progresso indica o andamento)
   - Varie levemente a posição do rosto entre as coletas para melhor precisão
5. Clique em **Cadastrar usuário**

Os usuários cadastrados aparecem na lista abaixo do formulário.

---

## 3. Verificar acesso

1. Clique na aba **Verificar**
2. Selecione a **área** que deseja acessar:
   - **Consulta geral** — nível 1 (qualquer usuário)
   - **Registros de toxinas** — nível 2 (diretores da divisão Toxinas + ministro)
   - **Registros de fiscalização** — nível 2 (diretores da divisão Fiscalização + ministro)
   - **Gabinete ministerial** — nível 3 (apenas ministro)
3. Posicione seu rosto na câmera
4. Clique em **Verificar agora** ou aguarde a verificação automática (a cada 2,5 segundos)
5. O resultado aparece no banner inferior:
   - **Verde (ACESSO PERMITIDO)** — usuário identificado e autorizado para a área
   - **Vermelho (ACESSO NEGADO)** — usuário não identificado ou sem permissão

---

## 4. Histórico

Clique na aba **Histórico** para ver o registro completo de todas as tentativas de acesso, com horário, nome, área e resultado.

---

## 5. Regras de autorização

| Área                     | Nível 1 | Nível 2 (Toxinas) | Nível 2 (Fiscalização) | Nível 3 (Ministro) |
|--------------------------|---------|-------------------|------------------------|---------------------|
| Consulta geral           | ✅      | ✅                | ✅                     | ✅                  |
| Registros de toxinas     | ❌      | ✅                | ❌                     | ✅                  |
| Registros de fiscalização| ❌      | ❌                | ✅                     | ✅                  |
| Gabinete ministerial     | ❌      | ❌                | ❌                     | ✅                  |

---

## 6. Limitações do protótipo

- **Dados em memória** — os cadastros são perdidos ao fechar ou recarregar a página
- **Pseudo-embeddings** — o reconhecimento facial usa vetores simplificados extraídos dos pixels da câmera (não usa FaceNet real no navegador)
- **Sem prova de vida** — o sistema não distingue uma foto de um rosto real
- **Sem persistência** — não há banco de dados; tudo roda localmente no navegador
- **Somente simulação** — o banner "ACESSO PERMITIDO" inclui o aviso "SOMENTE SIMULAÇÃO"

---

## 7. Requisitos

- Navegador moderno (Chrome 80+, Firefox 78+, Edge 80+)
- Câmera/webcam funcional
- Permissão de câmera concedida ao navegador
