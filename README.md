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
- [Limitações](#limitações)
- [Estrutura de Arquivos](#estrutura-de-arquivos)
- [Licença](#licença)

---

## 📖 Sobre o Projeto

O **Cofre Acadêmico** é um protótipo de sistema de controle de acesso baseado em reconhecimento facial, desenvolvido como trabalho acadêmico para a disciplina de **Visão Computacional**. O sistema simula o controle de acesso a áreas restritas de um órgão governamental fictício, com diferentes níveis de autorização.

O projeto roda inteiramente no navegador como uma **Single Page Application (SPA)** — sem backend, sem banco de dados, sem instalação.

---

## ✨ Funcionalidades

- **Reconhecimento facial via webcam** — captura de embeddings faciais diretamente no navegador
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
| **Canvas API** | Extração de pseudo-embeddings faciais (vetores 128D) |
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
│  │         Estado em Memória (React)       │ │
│  │  • users[]    • gallery{}   • attempts[]│ │
│  └─────────────────┬──────────────────────┘ │
│                    │                         │
│  ┌─────────────────▼──────────────────────┐ │
│  │        Motor de Reconhecimento          │ │
│  │  • Pseudo-embeddings 128D (Canvas)      │ │
│  │  • Distância Euclidiana + L2 Normalize  │ │
│  │  • Threshold: 0.8 / Margem: 0.1        │ │
│  └─────────────────┬──────────────────────┘ │
│                    │                         │
│  ┌─────────────────▼──────────────────────┐ │
│  │           WebRTC (getUserMedia)          │ │
│  │           Acesso à webcam               │ │
│  └────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

### Fluxo de verificação

1. A webcam captura um frame a cada 2,5 segundos
2. O frame é redimensionado para 32×32 px via Canvas
3. Um pseudo-embedding de 128 dimensões é extraído dos pixels
4. O vetor é normalizado (L2) e comparado com a galeria cadastrada
5. A menor distância Euclidiana determina a identidade
6. As regras de autorização verificam se o usuário tem acesso à área selecionada

---

## ⚠ Limitações

| Limitação | Descrição |
|---|---|
| **Dados em memória** | Os cadastros são perdidos ao fechar ou recarregar a página |
| **Pseudo-embeddings** | O reconhecimento usa vetores simplificados extraídos dos pixels (não usa FaceNet/dlib real) |
| **Sem prova de vida** | O sistema não distingue uma foto impressa de um rosto real |
| **Sem persistência** | Não há banco de dados; tudo roda localmente no navegador |
| **Sem criptografia** | Os embeddings não são cifrados em memória |
| **Somente simulação** | Não adequado para uso em produção |

---

## 📁 Estrutura de Arquivos

```
├── cofre-academico.html        # Front-end SPA (React 18, abre direto no navegador)
├── README.md                   # Este arquivo
├── MODO_DE_USO.md              # Guia de uso da versão web
└── projeto/                    # Backend Python + GUI desktop
    ├── core.py                 # Motor de reconhecimento (embeddings, matching, autorização)
    ├── vision.py               # Pipeline de visão computacional (FaceNet, MTCNN)
    ├── cofre.py                # CLI — ponto de entrada do backend
    ├── gui.py                  # Interface gráfica desktop (Tkinter)
    ├── evaluation.py           # Avaliação de desempenho do modelo
    ├── demo_sintetico.py       # Demonstração com dados sintéticos
    ├── test_core.py            # Testes unitários do core
    ├── test_vision.py          # Testes unitários da visão
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
