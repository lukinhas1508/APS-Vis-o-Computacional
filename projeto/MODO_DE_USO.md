# Modo de uso — Cofre Acadêmico com Reconhecimento Facial

> **Protótipo acadêmico.** Este sistema simula o controle de acesso a um
> cofre fictício do Ministério do Meio Ambiente contendo registros sobre
> toxinas. Ele **não aciona fechaduras físicas reais**, **não acessa
> sistemas governamentais reais** e **não utiliza documentos reais** do
> Ministério. Todas as liberações de acesso mostradas pelo sistema são
> **simuladas**. Não há prova de vida nem login administrativo: o cadastro
> pressupõe um operador local confiável, fisicamente presente junto ao
> computador.

## 1. Requisitos

- Python 3.11, 64 bits.
- Windows, Linux ou macOS. No Windows, a webcam usa o backend `CAP_DSHOW`;
  nos demais sistemas, `CAP_ANY`. O processamento funciona em CPU, sem
  exigir CUDA/GPU.

## 2. Instalação

```bash
python3 -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements.txt
```

Ajuda (`diagnostico`), preparação do modelo e a demonstração sintética
(`simular`) funcionam mesmo sem instalar `tensorflow`, `keras-facenet`,
`opencv-python` ou `mtcnn` — apenas as funcionalidades que dependem de
reconhecimento facial real exigem essas dependências.

## 3. Preparar o modelo de reconhecimento facial

O reconhecimento facial real usa pesos pré-treinados do modelo FaceNet
(identificador `facenet-20180402-114759-v1`). Por padrão, **nenhum download é
feito automaticamente**. Para baixar e validar os pesos (verificação por
SHA-256):

```bash
python3 cofre.py preparar-modelo
```

Se os pesos já existirem em `models/20180402-114759-weights.h5` e o hash
conferir, eles são reutilizados. Pesos locais com hash inválido são
rejeitados e **não são sobrescritos automaticamente**; remova o arquivo
manualmente ou execute `preparar-modelo` novamente.

## 4. Verificar o ambiente

```bash
python3 cofre.py diagnostico
```

Mostra a versão do Python, as versões das dependências instaladas e se os
pesos do modelo estão íntegros. **Este comando não testa a câmera nem executa
inferência real.**

## 5. Demonstração sintética (sem câmera, sem TensorFlow/OpenCV)

```bash
python3 cofre.py simular --saida reports/minha_simulacao
```

Executa nove casos com **vetores artificiais** (não derivados de rostos
reais) e falhas de aquisição **injetadas propositalmente**, gerando:

- `simulacao.sqlite3` — banco independente da demonstração;
- `tentativas.csv` — registro de todas as tentativas;
- `resumo.json` — contagem de permitidas/negadas.

Os números produzidos **não representam acurácia de reconhecimento facial**
— servem apenas para demonstrar o fluxo de decisão e auditoria.

## 6. Interface gráfica

```bash
python3 cofre.py gui --camera 0
```

- **Painel esquerdo**: escolha a área (`geral`, `toxinas`, `fiscalizacao` ou
  `ministerial`), importe uma imagem ou inicie a câmera, veja a decisão
  (`PERMITIDO — SOMENTE SIMULAÇÃO`, `NEGADO` ou `SEM AUTORIZAÇÃO`) e o
  histórico de tentativas. É possível exportar o histórico para CSV.
- **Painel direito**: cadastro administrativo local. Preencha ID, nome,
  nível (1 a 3) e, se o nível for 2, a divisão (Toxinas ou Fiscalização).
  Marque o consentimento explícito do titular antes de cadastrar. Colete ao
  menos três amostras (por webcam) da **mesma pessoa** — diferenças entre
  as imagens **não constituem prova de vida**.

Ao fechar a janela, a câmera e o banco de dados são liberados
automaticamente.

## 7. Linha de comando (CLI)

Opções globais (antes do subcomando): `--banco` (padrão
`data/cofre.sqlite3`), `--limiar` (padrão `0.8`), `--margem` (padrão `0.1`).

### Cadastrar um usuário

```bash
python3 cofre.py cadastrar --id ana --nome "Ana Souza" --nivel 2 \
    --divisao Toxinas --consentimento \
    imagens/ana_1.jpg imagens/ana_2.jpg imagens/ana_3.jpg
```

São necessárias pelo menos três imagens distintas da mesma pessoa.

### Verificar uma imagem

```bash
python3 cofre.py verificar imagens/visitante.jpg --area toxinas
```

Imprime a decisão em JSON e retorna um código de saída:

- `0` — acesso permitido (simulado);
- `1` — acesso negado;
- `2` — erro operacional ou de argumentos.

### Verificar continuamente pela webcam

```bash
python3 cofre.py webcam --area geral --camera 0
```

Mostra o vídeo e imprime decisões em JSON no terminal. Pressione **Q** ou
**Esc** para encerrar. Uma interrupção pelo teclado (Ctrl+C) também encerra
o comando — sem qualquer liberação física.

### Exportar o histórico de tentativas

```bash
python3 cofre.py exportar saida/tentativas.csv
```

Gera um CSV em UTF-8 com marca de ordem de bytes (BOM), com cabeçalho e
neutralização de valores que poderiam ser interpretados como fórmulas ao
abrir a planilha. Não é permitido exportar sobre o próprio arquivo do banco
SQLite.

### Avaliar o desempenho a partir de um manifesto rotulado

```bash
python3 cofre.py avaliar manifesto.csv --saida avaliacao/resultado_2026
```

O manifesto é um CSV com cabeçalho exato `image,user_id` (use `desconhecido`
para amostras que não devem corresponder a ninguém cadastrado). Gera
`metrics.json`, `predictions.csv` e `confusion_matrix.png`. **O limiar e a
margem padrão não estão calibrados** para uso real, e não há detecção
automática de vazamento entre conjuntos de cadastro, validação e teste —
isso é responsabilidade de quem organiza o manifesto.

## 8. Motivos de negação mais comuns

| Motivo | Significado |
|---|---|
| `nenhum_rosto` | Nenhum rosto foi detectado na imagem. |
| `multiplos_rostos` | Mais de um rosto foi detectado; o sistema nunca escolhe um automaticamente. |
| `rosto_pequeno` | O rosto detectado é menor que 80×80 pixels. |
| `imagem_desfocada` | Nitidez abaixo do limiar mínimo. |
| `iluminacao_inadequada` | Luminosidade fora da faixa aceitável (40–215). |
| `desconhecido` | Nenhuma identidade cadastrada está próxima o suficiente. |
| `identidade_ambigua` | Duas identidades ficaram próximas demais entre si. |
| `sem_autorizacao_nivel` | A pessoa foi identificada, mas seu nível/divisão não dá acesso à área escolhida. |

## 9. Limitações importantes

- Este é um protótipo acadêmico local; não há garantias de segurança para
  uso em produção.
- Não há prova de vida: o sistema não distingue uma pessoa real de uma foto
  de boa qualidade.
- O limiar (0.8) e a margem (0.1) padrão não foram calibrados para nenhum
  cenário real específico.
- O cadastro pressupõe um operador confiável fisicamente presente; não há
  autenticação de administrador.
