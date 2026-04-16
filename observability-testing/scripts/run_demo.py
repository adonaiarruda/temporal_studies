"""
Demo script — triggers 5 QA workflows and prints results.

Prerequisites:
  1. Temporal running: docker compose -f docker/docker-compose.yml up -d
  2. Worker running:   uv run python src/worker.py
  3. .env configured with BRAINTRUST_API_KEY

Usage:
    uv run python scripts/run_demo.py

After running, check:
  - Temporal UI  : http://localhost:8080  (workflow history, retries, payloads)
  - Braintrust   : https://www.braintrust.dev/app → project 'observability-demo' → Logs
                   (full trace tree: workflow → activities → LLM calls with tokens/cost)
"""
import asyncio
import os
import uuid

from dotenv import load_dotenv
from temporalio.client import Client

from src.workflows.qa_workflow import QAWorkflow, QAInput

load_dotenv()

TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = os.environ.get("TEMPORAL_TASK_QUEUE", "observability-demo")

# A mix of intents to exercise all classifier branches
DEMO_QUESTIONS = [
    "What is the capital of Japan?",                      # FACTUAL
    "How do I reverse a list in Python?",                 # PROCEDURAL
    "What is the difference between AI and ML?",          # DEFINITION
    "If I invest R$1000 at 10% per year for 5 years, what do I get?",  # CALCULATION
    "Is it better to use microservices or a monolith?",   # OPINION
]


async def run_workflow(client: Client, question: str) -> None:
    workflow_id = f"qa-demo-{uuid.uuid4().hex[:8]}"
    print(f"\n[{workflow_id}] Question: {question}")

    handle = await client.start_workflow(
        QAWorkflow.run,
        QAInput(question=question),
        id=workflow_id,
        task_queue=TASK_QUEUE,
    )

    result = await handle.result()

    print(f"  Intent    : {result.intent} ({result.confidence:.0%} confidence)")
    print(f"  Answer    : {result.answer[:250].strip()}{'...' if len(result.answer) > 250 else ''}")


async def main() -> None:
    print("=" * 60)
    print("  OBSERVABILITY DEMO — Temporal + Braintrust")
    print("=" * 60)
    print(f"  Temporal  : {TEMPORAL_HOST}")
    print(f"  Task queue: {TASK_QUEUE}")
    print(f"  Questions : {len(DEMO_QUESTIONS)}")
    print("=" * 60)

    client = await Client.connect(TEMPORAL_HOST)

    # Run all workflows — sequentially so the output is readable
    for question in DEMO_QUESTIONS:
        await run_workflow(client, question)

    print("\n" + "=" * 60)
    print("  Done. Open these to see the traces:")
    print("  Temporal UI  : http://localhost:8080")
    print("  Braintrust   : https://www.braintrust.dev/app")
    print("                 -> project 'observability-demo' -> Logs")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
