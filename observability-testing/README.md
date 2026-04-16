# Observability Frameworks — Análise Comparativa

> Demo funcional de **Temporal + Braintrust** com análise completa de , Braintrust.

---

## O que este projeto demonstra

| O que | Como |
|---|---|
| Online tracing | Worker Temporal com `BraintrustPlugin` → toda chamada LLM vira span |
| Custo, latência, tokens | Automático via Braintrust proxy (OpenAI-compatible) |
| Trace hierarchy | Workflow → Activity → LLM call, aninhados no Braintrust |
| Offline evaluation | `Eval()` com dataset + scorers (Factuality, IntentAccuracy, ClosedQA) |
| Retry visibility | Políticas de retry do Temporal visíveis como spans separados |


---

## Estrutura do Projeto

```
observability-comparison/
├── README.md                         # Este arquivo
├── pyproject.toml
├── .env.example
│
├── docker/
│   └── docker-compose.yml            # Temporal local (PostgreSQL + Server + UI)
│
├── src/
│   ├── llm_client.py                 # OpenAI SDK → Braintrust proxy → Claude
│   ├── prompts.py                    # Prompts centralizados (compartilhados com evals)
│   │
│   ├── workflows/
│   │   └── qa_workflow.py            # QAWorkflow: classify → answer
│   │
│   └── activities/
│       ├── classify_activity.py      # classify_question_activity
│       └── answer_activity.py        # answer_question_activity
│
├── evals/
│   ├── task.py                       # Pipeline sem Temporal (para Eval())
│   └── offline_eval.py               # Eval() com dataset + Factuality + IntentAccuracy
│
└── scripts/
    └── run_demo.py                   # Dispara 5 workflows e imprime resultados
```

---

## Setup

### Pré-requisitos

- Python 3.11+
- Docker
- Conta Braintrust com API key: [braintrust.dev/app/settings](https://www.braintrust.dev/app/settings?tab=api-keys)

### Configuração

```bash
# 1. Entrar no diretório
cd temporal_studies/observability-comparison

# 2. Copiar e preencher variáveis de ambiente
cp .env.example .env
# Edite .env: adicione BRAINTRUST_API_KEY (obrigatório)

# 3. Instalar dependências
pip install -r requirements.txt
```

### Rodar o demo de tracing online

```bash
# 1. Temporal local
docker compose -f docker/docker-compose.yml up -d
# UI: http://localhost:8080

# 2. Worker (terminal 1)
python src/worker.py

# 3. Disparar workflows (terminal 2)
python scripts/run_demo.py
```

Após executar, abra:
- **Temporal UI** → `http://localhost:8080` — histórico de eventos, payloads, retries
- **Braintrust** → `https://www.braintrust.dev/app` → projeto `observability-demo` → aba **Logs**
  - Cada workflow run = 1 trace com hierarquia: Workflow → Activity → LLM call
  - Tokens, custo e latência por nível

### Rodar avaliação offline

```bash
# Opção A — via CLI do Braintrust (recomendado, gera Experiment na UI)
braintrust run evals/offline_eval.py

# Opção B — direto com Python
python evals/offline_eval.py
```

Após executar, abra:
- **Braintrust** → projeto `observability-demo` → aba **Experiments**
  - Tabela com score de Factuality, IntentAccuracy e ClosedQA por caso de teste
  - Comparação entre experimentos ao longo do tempo

---

## Fluxo de Tracing (Online)

```
scripts/run_demo.py
        │
        │ start_workflow(QAWorkflow)
        ▼
┌─────────────────────────────────────────────────────┐
│              QAWorkflow  [Braintrust: task span]     │
│                                                     │
│  1. classify_question_activity                      │
│     [Braintrust: task span]                         │
│       └── POST /v1/proxy  [llm span]                │
│             tokens: 45 in + 32 out                  │
│             cost: $0.00004                          │
│             latency: 312ms                          │
│                                                     │
│  2. answer_question_activity                        │
│     [Braintrust: task span]                         │
│       └── POST /v1/proxy  [llm span]                │
│             tokens: 180 in + 420 out                │
│             cost: $0.00061                          │
│             latency: 1840ms                         │
└─────────────────────────────────────────────────────┘
        │
        ▼
  QAResult { intent, confidence, answer }
```

## Fluxo de Avaliação Offline

```
evals/offline_eval.py
        │
        │ Eval("qa-pipeline-eval", data=DATASET, task=task, scores=[...])
        ▼
┌─────────────────────────────────────────────────────┐
│  Para cada item do dataset (10 casos):               │
│                                                     │
│  task(question)                                     │
│    ├── classify_and_answer(question)                │
│    │     ├── call_llm(CLASSIFY_SYSTEM, ...)         │
│    │     └── call_llm(ANSWER_SYSTEM[intent], ...)   │
│    └── retorna {"intent": ..., "answer": ...}       │
│                                                     │
│  Scorers:                                           │
│    ├── Factuality(output.answer, expected)  → 0-1   │
│    ├── intent_accuracy(output.intent, meta) → 0 ou 1│
│    └── ClosedQA(question, output.answer)    → 0-1   │
└─────────────────────────────────────────────────────┘
        │
        ▼
  Experimento salvo no Braintrust
  (comparável com runs anteriores)
```

---

## Conceitos Temporais Exercitados

| Conceito | Onde |
|---|---|
| **Workflow** | `QAWorkflow` — execução durável e rastreável |
| **Activity** | `classify_question`, `answer_question` |
| **RetryPolicy** | Backoff exponencial, máx 3 tentativas — cada retry vira span separado no Braintrust |
| **Schedule-to-close timeout** | `timedelta(minutes=2)` por activity |
| **Plugin** | `BraintrustPlugin` — intercepta worker sem modificar workflow/activity |

## Referências

- [Temporal + Braintrust Integration Blog Post](https://temporal.io/blog/building-observable-ai-agents-temporal-now-integrates-with-braintrust)
- [Braintrust Python SDK](https://www.braintrust.dev/docs/libs/python)
- [Braintrust Tracing Guide](https://www.braintrust.dev/docs/guides/tracing)
- [autoevals Library](https://www.braintrust.dev/docs/reference/autoevals)
- [LangSmith Docs](https://docs.smith.langchain.com/)
- [Langfuse Docs](https://langfuse.com/docs)
- [Temporal Python Dev Guide](https://docs.temporal.io/develop/python)
