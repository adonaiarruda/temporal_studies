# CLAUDE.md — PreFi Lite Demo

> Guia de contexto para o Claude Code trabalhar neste repositório.
> Projeto demo educacional: aprender Temporal + AWS Bedrock com um caso de uso real.

---

## 🎯 O que é este projeto

**PreFi Lite** é uma simulação simplificada do fluxo do Clarity Engine (PreFi).

O usuário descreve sua situação financeira em **texto livre**. O sistema detecta seu
estado emocional e gera um cenário de refinanciamento adaptado ao seu perfil.

A conversa flui naturalmente — o usuário pode continuar enviando mensagens a qualquer
momento. Se quiser, pode avaliar uma resposta (nota 1–5 + feedback), o que dispara
**um novo workflow independente** que regenera o cenário incorporando o feedback.

### Dois workflows distintos

| Workflow | Trigger | O que faz |
|---|---|---|
| `AnalysisWorkflow` | Usuário envia mensagem | Detecta emoção → gera cenário → retorna |
| `RefinementWorkflow` | Usuário avalia com nota ≤ 3 | Regenera cenário com histórico + feedback |

Nenhum workflow pausa esperando o outro. São execuções independentes e assíncronas.

---

## 🔄 Fluxos

### Fluxo principal (sempre acontece)

```
Usuário (texto livre)
        │
        ▼
POST /analysis/start
        │
        ▼
┌─────────────────────────────────────┐
│         AnalysisWorkflow            │
│                                     │
│  1. detect_emotion_activity()       │
│     → Bedrock: ansioso | confuso |  │
│       confiante | frustrado         │
│                                     │
│  2. generate_scenario_activity()    │
│     → Bedrock: cenário adaptado     │
│       ao estado emocional           │
│                                     │
│  3. Retorna resultado               │
└─────────────────────────────────────┘
        │
        ▼
GET /analysis/{id}/result
```

### Fluxo de refinamento (opcional, disparado pelo usuário)

```
Usuário avalia: nota ≤ 3 + feedback
        │
        ▼
POST /refinement/start
Body: { analysis_id, nota, feedback }
        │
        ▼
┌──────────────────────────────────────────┐
│           RefinementWorkflow             │
│                                          │
│  1. Busca contexto do AnalysisWorkflow   │
│     anterior (mensagem + estado + cen.)  │
│                                          │
│  2. generate_scenario_activity()         │
│     → Bedrock: regenera cenário usando   │
│       histórico + feedback do usuário    │
│                                          │
│  3. Retorna novo cenário                 │
└──────────────────────────────────────────┘
        │
        ▼
GET /refinement/{id}/result
```

---

## 🏗️ Arquitetura

```
┌──────────────────────────────────────────────────────┐
│                  FastAPI (API REST)                   │
│  POST /analysis/start         → inicia AnalysisWF    │
│  GET  /analysis/{id}/result   → resultado            │
│                                                      │
│  POST /refinement/start       → inicia RefinementWF  │
│  GET  /refinement/{id}/result → novo cenário         │
└──────────────────┬───────────────────────────────────┘
                   │ Temporal Client
                   ▼
┌──────────────────────────────────────────────────────┐
│             Temporal Server (local Docker)            │
└──────────────────┬───────────────────────────────────┘
                   │
          ┌────────┴────────┐
          ▼                 ▼
┌──────────────────┐  ┌──────────────────────┐
│ AnalysisWorkflow │  │  RefinementWorkflow   │
│  detect_emotion  │  │  generate_scenario   │
│  gen_scenario    │  │  (com histórico)      │
└──────────────────┘  └──────────────────────┘
          │                 │
          └────────┬────────┘
                   │ boto3
                   ▼
┌──────────────────────────────────────────────────────┐
│          AWS Bedrock (Claude claude-3-5-sonnet)       │
└──────────────────────────────────────────────────────┘
```

---

## 📁 Estrutura de Diretórios

```
prefi-lite/
├── CLAUDE.md
├── README.md
├── pyproject.toml
├── .env.example
│
├── src/
│   ├── __init__.py
│   ├── api.py                          # FastAPI — todos os endpoints
│   ├── worker.py                       # Entry point do Temporal worker
│   ├── bedrock_client.py               # Wrapper boto3 Bedrock
│   │
│   ├── workflows/
│   │   ├── __init__.py
│   │   ├── analysis_workflow.py        # Fluxo principal
│   │   └── refinement_workflow.py      # Fluxo de refinamento
│   │
│   └── activities/
│       ├── __init__.py
│       ├── emotion_detection.py        # Detecta estado emocional
│       ├── scenario_generation.py      # Gera cenário (com ou sem feedback)
│       └── notification.py            # Loga resultado final
│
├── prompts/
│   ├── emotion_detection.txt
│   └── scenario_generation.txt
│
├── tests/
│   ├── unit/
│   │   ├── test_analysis_workflow.py
│   │   ├── test_refinement_workflow.py
│   │   └── test_activities.py
│   └── integration/
│       └── test_e2e.py
│
└── docker/
    └── docker-compose.yml
```

---

## 🧠 Conceitos Temporais Exercitados

| Conceito | Onde aparece |
|---|---|
| **Workflow** | `AnalysisWorkflow` e `RefinementWorkflow` — execuções independentes |
| **Activity** | `detect_emotion`, `generate_scenario`, `notify` |
| **Retry Policy** | Activities do Bedrock: backoff exponencial, máx 3 tentativas |
| **Timeout** | `schedule_to_close_timeout` por activity |
| **Workflow ID determinístico** | `RefinementWorkflow` usa `analysis_id` para rastrear histórico |
| **Query** | `get_status` — consulta estado de qualquer workflow em execução |
| **Múltiplos workflows independentes** | Padrão de composição sem acoplamento direto |

> **Nota:** este projeto usa Workflows simples (run-to-completion) sem Signal/wait_condition.
> Isso é intencional — o padrão de pausa ficaria para uma evolução futura.

---

## 🤖 Prompts (prompts/)

### emotion_detection.txt
```
Você é um classificador de estado emocional para uma plataforma financeira.

Analise a mensagem abaixo e classifique o estado emocional do usuário em
EXATAMENTE uma das categorias:

- ANSIOSO: preocupação, medo de errar, urgência, insegurança financeira
- CONFUSO: não entende os termos, faz perguntas básicas, parece perdido
- CONFIANTE: tom assertivo, já pesquisou, sabe o que quer
- FRUSTRADO: já tentou antes e não conseguiu, irritação, descrença

Responda SOMENTE com JSON, sem explicações:
{"estado": "ANSIOSO"|"CONFUSO"|"CONFIANTE"|"FRUSTRADO", "confianca": 0.0-1.0, "justificativa": "..."}

Mensagem do usuário:
{mensagem}
```

### scenario_generation.txt
```
Você é um assistente de educação financeira para refinanciamento imobiliário.

Tom a usar com base no estado emocional detectado:
- ANSIOSO: calmo, reassuring, passo a passo, sem jargão
- CONFUSO: didático, analogias simples, definições curtas
- CONFIANTE: direto, técnico, com números
- FRUSTRADO: empático, reconhece a dificuldade, mostra caminho concreto

Estado detectado: {estado_emocional}

{contexto_anterior}

Com base na situação descrita abaixo, gere 2 cenários de refinanciamento
simplificados (Cenário Conservador e Cenário Otimizado).
Para cada cenário inclua: objetivo, prazo estimado, próximo passo concreto.
Não faça recomendações — apresente opções neutras.

Situação do usuário:
{mensagem}
```

> `{contexto_anterior}` é vazio no `AnalysisWorkflow`. No `RefinementWorkflow`,
> é preenchido com o cenário anterior + nota + feedback do usuário.

---

## 🔌 API Endpoints

```
# Fluxo principal
POST /analysis/start
Body:     {"mensagem": "Quero refinanciar minha casa mas tenho medo de errar..."}
Response: {"workflow_id": "analysis-abc123", "status": "running"}

GET /analysis/{id}/result
Response: {
  "workflow_id": "analysis-abc123",
  "estado_emocional": "ANSIOSO",
  "confianca_emocao": 0.91,
  "cenario": "...",
  "status": "completed"
}

# Fluxo de refinamento (usuário insatisfeito)
POST /refinement/start
Body: {
  "analysis_id": "analysis-abc123",
  "nota": 2,
  "feedback": "Muito técnico, não entendi nada"
}
Response: {"workflow_id": "refinement-xyz456", "status": "running"}

GET /refinement/{id}/result
Response: {
  "workflow_id": "refinement-xyz456",
  "analysis_id": "analysis-abc123",
  "cenario_refinado": "...",
  "status": "completed"
}
```

---

## 📝 Esqueletos dos Workflows

### AnalysisWorkflow

```python
# src/workflows/analysis_workflow.py
from temporalio import workflow
from temporalio.common import RetryPolicy
from dataclasses import dataclass
from datetime import timedelta

@dataclass
class AnalysisInput:
    mensagem: str

@dataclass
class AnalysisResult:
    estado_emocional: str
    confianca_emocao: float
    cenario: str

@workflow.defn
class AnalysisWorkflow:

    @workflow.run
    async def run(self, input: AnalysisInput) -> AnalysisResult:
        retry = RetryPolicy(
            initial_interval=timedelta(seconds=2),
            backoff_coefficient=2.0,
            maximum_attempts=3,
        )
        timeout = timedelta(minutes=2)

        # 1. Detectar emoção
        emocao = await workflow.execute_activity(
            "detect_emotion_activity",
            input.mensagem,
            schedule_to_close_timeout=timeout,
            retry_policy=retry,
        )

        # 2. Gerar cenário
        cenario = await workflow.execute_activity(
            "generate_scenario_activity",
            {
                "mensagem": input.mensagem,
                "estado": emocao["estado"],
                "contexto_anterior": "",
            },
            schedule_to_close_timeout=timeout,
            retry_policy=retry,
        )

        return AnalysisResult(
            estado_emocional=emocao["estado"],
            confianca_emocao=emocao["confianca"],
            cenario=cenario,
        )
```

### RefinementWorkflow

```python
# src/workflows/refinement_workflow.py
from temporalio import workflow
from temporalio.common import RetryPolicy
from dataclasses import dataclass
from datetime import timedelta

@dataclass
class RefinementInput:
    analysis_id: str
    mensagem_original: str
    cenario_anterior: str
    estado_emocional: str
    nota: int
    feedback: str

@dataclass
class RefinementResult:
    analysis_id: str
    cenario_refinado: str

@workflow.defn
class RefinementWorkflow:

    @workflow.run
    async def run(self, input: RefinementInput) -> RefinementResult:
        retry = RetryPolicy(
            initial_interval=timedelta(seconds=2),
            backoff_coefficient=2.0,
            maximum_attempts=3,
        )

        contexto = (
            f"Cenário anterior gerado:\n{input.cenario_anterior}\n\n"
            f"Avaliação do usuário: {input.nota}/5\n"
            f"Feedback: {input.feedback}"
        )

        cenario_refinado = await workflow.execute_activity(
            "generate_scenario_activity",
            {
                "mensagem": input.mensagem_original,
                "estado": input.estado_emocional,
                "contexto_anterior": contexto,
            },
            schedule_to_close_timeout=timedelta(minutes=2),
            retry_policy=retry,
        )

        return RefinementResult(
            analysis_id=input.analysis_id,
            cenario_refinado=cenario_refinado,
        )
```

---

## ⚙️ Setup

### Dependências (pyproject.toml)
```toml
[project]
name = "prefi-lite"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "temporalio>=1.7",
    "boto3>=1.35",
    "fastapi>=0.115",
    "uvicorn",
    "pydantic>=2.0",
    "python-dotenv",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio", "httpx", "moto[bedrock]"]
```

### .env.example
```
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_DEFAULT_REGION=us-east-1
BEDROCK_MODEL_ID=us.anthropic.claude-3-5-sonnet-20241022-v2:0
TEMPORAL_HOST=localhost:7233
TEMPORAL_TASK_QUEUE=prefi-lite
```

### Subir e rodar
```bash
# 1. Temporal local
docker compose -f docker/docker-compose.yml up -d
# UI: http://localhost:8080

# 2. Instalar deps
uv sync

# 3. Worker em background
uv run python src/worker.py &

# 4. API
uv run uvicorn src.api:app --reload
# Docs: http://localhost:8000/docs
```

---

## 🚀 Roadmap de Aprendizado

```
Fase 1 — AnalysisWorkflow
  ⬜ Temporal local rodando (Docker)
  ⬜ Worker registrado com AnalysisWorkflow + Activities
  ⬜ Activity detect_emotion chamando Bedrock
  ⬜ Activity generate_scenario chamando Bedrock
  ⬜ FastAPI: POST /analysis/start + GET /analysis/{id}/result

Fase 2 — RefinementWorkflow
  ⬜ RefinementWorkflow recebendo contexto do Analysis anterior
  ⬜ Prompt de geração usando cenário anterior + feedback
  ⬜ FastAPI: POST /refinement/start + GET /refinement/{id}/result

Fase 3 — Resiliência
  ⬜ Retry policy testada (simular falha no Bedrock)
  ⬜ Timeouts configurados e verificados na Temporal UI

Fase 4 — Observabilidade
  ⬜ Temporal UI: histórico de eventos dos dois workflows
  ⬜ Logs estruturados por workflow_id
```

---

## ⚠️ Regras para o Claude Code

1. **Nunca colocar boto3 / I/O dentro de Workflows** — apenas em Activities
2. **Nunca usar `datetime.now()`, `random`, `time.sleep()` dentro de Workflows**
   — usar `workflow.now()` e `workflow.sleep()`
3. **Payloads entre Workflow e Activities devem ser `@dataclass` ou `dict` simples**
   — sem objetos boto3 ou LangChain
4. **Prompts vivem em `prompts/`** — nunca hardcoded nas Activities
5. **Task queue nomeada via variável de ambiente** `TEMPORAL_TASK_QUEUE`
6. **Testes de Workflow usam `WorkflowEnvironment.start_time_skipping()`**
7. **`RefinementWorkflow` recebe todo o contexto necessário no input** — não consulta
   o `AnalysisWorkflow` diretamente; o cliente (API) é responsável por buscar e
   passar o contexto

---

## 📚 Referências

- [Temporal Python Dev Guide](https://docs.temporal.io/develop/python)
- [Temporal Python API Reference](https://python.temporal.io/)
- [AWS Bedrock Python Getting Started](https://docs.aws.amazon.com/bedrock/latest/userguide/getting-started-api-ex-python.html)
- [Temporal Testing](https://docs.temporal.io/develop/python/testing-suite)