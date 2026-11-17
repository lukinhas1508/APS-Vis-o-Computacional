# 🔐 Cofre Acadêmico — Controle de Acesso por Reconhecimento Facial

Sistema de controle de acesso por reconhecimento facial para o cofre do **Ministério do Meio Ambiente** (protótipo acadêmico).

> **⚠ Projeto acadêmico — SOMENTE SIMULAÇÃO.** Não utilizar em ambientes reais de segurança.

---

## 📋 Sumário

- [Sobre o Projeto](#sobre-o-projeto)
- [Funcionalidades](#funcionalidades)
- [Tecnologias Utilizadas](#tecnologias-utilizadas)
- [Como Executar](#como-executar)
- [Regras de Autorização](#regras-de-autorização)
- [Arquitetura](#arquitetura)
- [Estrutura de Arquivos](#estrutura-de-arquivos)
- [Licença](#licença)

---

## 📖 Sobre o Projeto

O **Cofre Acadêmico** é um protótipo de sistema de controle de acesso baseado em reconhecimento facial, desenvolvido como trabalho acadêmico para a disciplina de **Visão Computacional**. O sistema simula o controle de acesso a áreas restritas de um órgão governamental fictício, com diferentes níveis de autorização.

O projeto roda inteiramente no navegador como uma **Single Page Application (SPA)** — sem backend, sem banco de dados, sem instalação.

---

## ✨ Funcionalidades

- **Reconhecimento facial via webcam** — captura de embeddings faciais diretamente no navegador
- **Prova de vida ativa** — desafio aleatório (piscar, virar o rosto, abrir a boca); fotos e imagens paradas são bloqueadas
- **Cadastro de usuários** com coleta de múltiplas amostras faciais
- **3 níveis de acesso** hierárquicos (Básico, Diretor, Ministro)
- **4 áreas protegidas** com regras de autorização distintas
- **Verificação automática** a cada 2,5 segundos quando a câmera está ativa
- **Histórico completo** de todas as tentativas de acesso
- **Remoção de perfis** cadastrados
- **Interface responsiva** — funciona em desktop, tablet e celular
- **HTML semântico** com atributos ARIA para acessibilidade
- **Dark/Light mode** automático (segue preferência do sistema)

---

## 🛠 Tecnologias Utilizadas

| Tecnologia | Uso |
|---|---|
| **React 18** (UMD + Babel Standalone) | Interface reativa em arquivo único |
| **WebRTC** (`getUserMedia`) | Captura de vídeo da webcam |
| **MediaPipe Face Landmarker** | Rastreamento facial (478 pontos + blendshapes) para a prova de vida e o recorte do rosto |
| **Canvas API** | Extração de embeddings faciais avançados (HOG + LBP + cor, 128D) |
| **Web Crypto API** | Criptografia AES-256-GCM dos embeddings armazenados |
| **IndexedDB** | Persistência local dos cadastros, galeria e histórico |
| **CSS Custom Properties** | Design tokens com suporte a dark/light mode |
| **General Sans** + **Commit Mono** | Tipografia — sem fontes "padrão de IA" |
| **SVG Icon System** | Ícones vetoriais inline (sem emoji/Unicode) |
| **HTML5 Semântico** | `<header>`, `<main>`, `<nav>`, `<section>`, `<aside>`, `<form>`, `<fieldset>`, `<output>`, `<time>` |
| **ARIA** | `aria-current`, `aria-pressed`, `aria-live`, `aria-label`, `role="progressbar"` |
| **Media Queries** | Breakpoints em 900px, 600px e 380px |

---

## 🚀 Como Executar

### Versão Web (SPA) — `cofre-academico.html`

1. Baixe o arquivo `cofre-academico.html`
2. Abra-o diretamente no navegador (Chrome, Edge ou Firefox)
3. Ao abrir, o navegador pedirá permissão para acessar a câmera — clique em **Permitir**
4. A câmera ligará automaticamente

> **Importante:** o arquivo deve ser aberto diretamente no navegador (`file://`), não dentro de iframes ou visualizadores embutidos.

**Requisitos:** Navegador moderno (Chrome 80+, Firefox 78+, Edge 80+), câmera/webcam funcional.

### Versão Desktop (Python) — `projeto/`

```bash
cd projeto
pip install -r requirements.txt
python cofre.py
```

**Requisitos:** Python 3.10+, pip, câmera/webcam funcional. Consulte `projeto/MODO_DE_USO.md` para instruções detalhadas.

---

## 🔑 Regras de Autorização

O sistema implementa 3 níveis de acesso e 2 divisões:

| Área | Nível 1 (Básico) | Nível 2 (Toxinas) | Nível 2 (Fiscalização) | Nível 3 (Ministro) |
|---|:---:|:---:|:---:|:---:|
| Consulta geral | ✅ | ✅ | ✅ | ✅ |
| Registros de toxinas | ❌ | ✅ | ❌ | ✅ |
| Registros de fiscalização | ❌ | ❌ | ✅ | ✅ |
| Gabinete ministerial | ❌ | ❌ | ❌ | ✅ |

- **Nível 1 (Básico)** — acesso apenas à consulta geral
- **Nível 2 (Diretor)** — acesso à consulta geral + registros da própria divisão
- **Nível 3 (Ministro)** — acesso a todas as áreas (apenas um permitido no sistema)

---

## 🏗 Arquitetura

```
┌─────────────────────────────────────────────┐
│                  Navegador                   │
├─────────────────────────────────────────────┤
│  React 18 SPA (arquivo único)               │
│  ┌───────────┐  ┌────────────┐  ┌────────┐ │
│  │  Cadastro  │  │ Verificação│  │Histórico│ │
│  └─────┬─────┘  └─────┬──────┘  └────┬───┘ │
│        │               │              │      │
│  ┌─────▼───────────────▼──────────────▼───┐ │
│  │      IndexedDB + AES-256-GCM           │ │
│  │  • users[]    • gallery{}   • attempts[]│ │
│  │  • Embeddings cifrados (Web Crypto API) │ │
│  └─────────────────┬──────────────────────┘ │
│                    │                         │
│  ┌─────────────────▼──────────────────────┐ │
│  │        Motor de Reconhecimento v2       │ │
│  │  • HOG + LBP + cor + stats (128D)       │ │
│  │  • Distância Euclidiana + L2 Normalize  │ │
│  │  • Threshold: 0.8 / Margem: 0.1        │ │
│  └─────────────────┬──────────────────────┘ │
│                    │                         │
│  ┌─────────────────▼──────────────────────┐ │
│  │       Detecção de vivacidade            │ │
│  │  • MediaPipe Face Landmarker (478 pts)  │ │
│  │  • Desafio aleatório: piscar/virar/boca │ │
│  └─────────────────┬──────────────────────┘ │
│                    │                         │
│  ┌─────────────────▼──────────────────────┐ │
│  │           WebRTC (getUserMedia)          │ │
│  │          Acesso à webcam (64×64)        │ │
│  └────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

### Fluxo de verificação

1. A webcam é rastreada ~12×/s pelo **MediaPipe Face Landmarker** (478 pontos + blendshapes)
2. **Prova de vida ativa**: um desafio de 3 etapas é sorteado — sempre **piscar** + 2 entre **virar à esquerda**, **virar à direita** e **abrir a boca** (com retorno à posição frontal entre etapas, 8 s por etapa)
3. O giro é medido pela projeção da ponta do nariz no eixo entre os cantos dos olhos (paralaxe 3D) — inclinar, girar ou balançar uma **foto** não altera essa medida
4. A aprovação vale 20 s **enquanto o mesmo rosto continuar no quadro**; rosto perdido, 2 rostos ou troca brusca reiniciam o desafio
5. Sem prova de vida aprovada → acesso negado (`prova_de_vida_pendente`). Sem o MediaPipe → tudo negado (falha fechada)
6. Somente o **recorte do rosto** é redimensionado para 64×64 px e vira um embedding 128D: HOG (64) + LBP (32) + cor (16) + stats (16)
7. O vetor é normalizado (L2) e comparado com a galeria cadastrada (cifrada com AES-256)
8. A menor distância Euclidiana determina a identidade
9. As regras de autorização verificam se o usuário tem acesso à área selecionada

O cadastro também exige prova de vida, e todas as amostras precisam vir da mesma sessão.
Na versão desktop (`projeto/`), a mesma lógica está em `liveness.py` (MediaPipe Face Mesh); verificação por arquivo de imagem é sempre negada.

### Testes da prova de vida

```bash
node --test tests/liveness-engine.test.js          # versão web
cd projeto && python -m unittest test_liveness     # versão desktop
```

> **Limitação:** a prova de vida bloqueia fotos impressas, fotos na tela do celular e imagens paradas, mas não cobre ataques avançados (vídeo/deepfake em tempo real controlado por um atacante, máscaras 3D).

---

## 📁 Estrutura de Arquivos

```
├── cofre-academico.html        # Front-end SPA (React 18, abre direto no navegador)
├── README.md                   # Este arquivo
├── MODO_DE_USO.md              # Guia de uso da versão web
├── tests/liveness-engine.test.js  # Testes da prova de vida (web)
└── projeto/                    # Backend Python + GUI desktop
    ├── core.py                 # Motor de reconhecimento (embeddings, matching, autorização)
    ├── vision.py               # Pipeline de visão computacional (FaceNet, MTCNN)
    ├── liveness.py             # Prova de vida ativa (MediaPipe Face Mesh)
    ├── cofre.py                # CLI — ponto de entrada do backend
    ├── gui.py                  # Interface gráfica desktop (Tkinter)
    ├── evaluation.py           # Avaliação de desempenho do modelo
    ├── demo_sintetico.py       # Demonstração com dados sintéticos
    ├── test_core.py            # Testes unitários do core
    ├── test_vision.py          # Testes unitários da visão
    ├── test_liveness.py        # Testes da prova de vida
    ├── requirements.txt        # Dependências Python
    ├── MODO_DE_USO.md          # Guia de uso da versão desktop
    ├── .gitignore
    ├── avaliacao/              # Resultados de avaliação
    ├── data/                   # Dados de faces cadastradas
    ├── models/                 # Modelos treinados
    └── reports/                # Relatórios de simulação
```

---

## 📄 Licença

Projeto acadêmico desenvolvido para fins educacionais. Uso livre para estudo e referência.
