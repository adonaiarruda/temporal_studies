"""
Temporal worker with Braintrust observability.

Key line: `plugins=[BraintrustPlugin()]`

What BraintrustPlugin does:
- Intercepts every Workflow execution → creates a root Braintrust span
- Intercepts every Activity execution → creates a child span nested under the workflow
- Propagates trace context across async boundaries automatically
- The LLM calls inside activities (via wrap_openai) attach as LLM child spans

Result in Braintrust UI (Logs tab):
  Each workflow run = one trace with full hierarchy of spans, tokens, costs, latency.
"""
import asyncio
import logging
import os

from dotenv import load_dotenv
from temporalio.client import Client
from temporalio.worker import Worker
from braintrust.contrib.temporal import BraintrustPlugin

from src.workflows.qa_workflow import QAWorkflow
from src.activities.classify_activity import classify_question
from src.activities.answer_activity import answer_question

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = os.environ.get("TEMPORAL_TASK_QUEUE", "observability-demo")
BRAINTRUST_PROJECT = os.environ.get("BRAINTRUST_PROJECT", "observability-demo")


async def main() -> None:
    client = await Client.connect(TEMPORAL_HOST)

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[QAWorkflow],
        activities=[classify_question, answer_question],
        plugins=[BraintrustPlugin()],
    )

    print(f"[worker] task queue  : {TASK_QUEUE}")
    print(f"[worker] braintrust  : project='{BRAINTRUST_PROJECT}'")
    print(f"[worker] temporal UI : http://localhost:8080")
    print(f"[worker] braintrust  : https://www.braintrust.dev/app")
    print("[worker] waiting for workflows...")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
