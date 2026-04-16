"""
Demo script — dispara 4 workflows de análise e, para o primeiro com nota baixa,
dispara também um workflow de refinamento.

Pré-requisitos:
  1. Temporal rodando : docker compose -f docker/docker-compose.yml up -d
  2. Worker rodando   : python -m src.worker
  3. .env com BRAINTRUST_API_KEY configurada

Uso:
    python scripts/run_demo.py

Após rodar, abra:
  - Temporal UI  : http://localhost:8080  (histórico de eventos, retries, payloads)
  - Braintrust   : https://www.braintrust.dev/app -> projeto 'prefi-lite' -> Logs
                   (árvore de spans: workflow → activities → LLM com tokens/custo)
"""
import asyncio
import os
import uuid

import braintrust
from braintrust.contrib.temporal import BraintrustPlugin
from dotenv import load_dotenv
from temporalio.client import Client

from src.workflows.analysis_workflow import AnalysisInput, AnalysisResult, AnalysisWorkflow
from src.workflows.refinement_workflow import RefinementInput, RefinementResult, RefinementWorkflow

load_dotenv()

TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = os.environ.get("TEMPORAL_TASK_QUEUE", "prefi-lite")
BRAINTRUST_PROJECT = os.environ.get("BRAINTRUST_PROJECT", "prefi-lite")

braintrust.init_logger(project=BRAINTRUST_PROJECT)

# Mensagens que exercitam os 4 estados emocionais
DEMO_MESSAGES = [
    ("ANSIOSO",    "Quero refinanciar minha casa mas tenho muito medo de errar e me endividar mais. Não sei nem por onde começar."),
    ("CONFUSO",    "O gerente falou em amortização e taxa efetiva mas não entendi nada. O que significa refinanciar exatamente?"),
    ("CONFIANTE",  "Já pesquisei as taxas dos principais bancos. Meu imóvel vale 600k e quero liberar 150k. Qual a melhor estratégia?"),
    ("FRUSTRADO",  "Tentei refinanciar duas vezes e os bancos negaram. Tenho score 620. Existe alguma saída real ou é perda de tempo?"),
]


async def run_analysis(client: Client, mensagem: str) -> tuple[str, AnalysisResult]:
    workflow_id = f"analysis-demo-{uuid.uuid4().hex[:8]}"

    handle = await client.start_workflow(
        AnalysisWorkflow.run,
        AnalysisInput(mensagem=mensagem),
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    result: AnalysisResult = await handle.result()
    return workflow_id, result


async def run_refinement(
    client: Client,
    analysis_id: str,
    analysis: AnalysisResult,
    nota: int,
    feedback: str,
) -> RefinementResult:
    workflow_id = f"refinement-demo-{uuid.uuid4().hex[:8]}"

    handle = await client.start_workflow(
        RefinementWorkflow.run,
        RefinementInput(
            analysis_id=analysis_id,
            mensagem_original=analysis.mensagem,
            cenario_anterior=analysis.cenario,
            estado_emocional=analysis.estado_emocional,
            nota=nota,
            feedback=feedback,
        ),
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    return await handle.result()


async def main() -> None:
    print("=" * 65)
    print("  PREFI LITE DEMO — Temporal + Braintrust")
    print("=" * 65)
    print(f"  Temporal   : {TEMPORAL_HOST}")
    print(f"  Task queue : {TASK_QUEUE}")
    print(f"  Braintrust : project='{BRAINTRUST_PROJECT}'")
    print(f"  Análises   : {len(DEMO_MESSAGES)}")
    print("=" * 65)

    client = await Client.connect(TEMPORAL_HOST, plugins=[BraintrustPlugin()])

    first_analysis_id: str | None = None
    first_analysis_result: AnalysisResult | None = None

    with braintrust.start_span(name="prefi-lite-demo"):
        for expected_state, mensagem in DEMO_MESSAGES:
            print(f"\n[esperado: {expected_state}]")
            print(f"  Mensagem : {mensagem[:80]}{'...' if len(mensagem) > 80 else ''}")

            workflow_id, result = await run_analysis(client, mensagem)

            print(f"  workflow_id      : {workflow_id}")
            print(f"  estado detectado : {result.estado_emocional} (confiança {result.confianca_emocao:.0%})")
            print(f"  cenário          : {result.cenario[:200].strip()}...")

            if first_analysis_id is None:
                first_analysis_id = workflow_id
                first_analysis_result = result

        # Refinamento: simula usuário insatisfeito com a primeira análise
        print("\n" + "-" * 65)
        print("  REFINAMENTO — nota 2/5 na primeira análise")
        print("-" * 65)

        feedback = "Muito técnico, não entendi nada. Precisa ser mais simples."
        refined = await run_refinement(
            client,
            analysis_id=first_analysis_id,
            analysis=first_analysis_result,
            nota=2,
            feedback=feedback,
        )

        print(f"  analysis_id     : {refined.analysis_id}")
        print(f"  feedback enviado: {feedback}")
        print(f"  cenário refinado: {refined.cenario_refinado[:200].strip()}...")

    print("\n" + "=" * 65)
    print("  Pronto. Abra para ver os traces:")
    print(f"  Temporal UI : http://localhost:8080")
    print(f"  Braintrust  : https://www.braintrust.dev/app")
    print(f"                -> projeto '{BRAINTRUST_PROJECT}' -> Logs")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
