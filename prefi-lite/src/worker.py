import asyncio
import logging
import os
from braintrust import init_logger
from braintrust.contrib.temporal import BraintrustPlugin
from dotenv import load_dotenv
from temporalio.client import Client
from temporalio.worker import Worker

from src.workflows.analysis_workflow import AnalysisWorkflow
from src.workflows.refinement_workflow import RefinementWorkflow
from src.activities.emotion_detection import detect_emotion_activity
from src.activities.scenario_generation import generate_scenario_activity
from src.activities.notification import notify_activity

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

TEMPORAL_HOST = os.environ.get("TEMPORAL_HOST", "localhost:7233")
TASK_QUEUE = os.environ.get("TEMPORAL_TASK_QUEUE", "prefi-lite")
BRAINTRUST_PROJECT = os.environ.get("BRAINTRUST_PROJECT", "prefi-lite")

init_logger(project=BRAINTRUST_PROJECT)


async def main():
    client = await Client.connect(TEMPORAL_HOST)

    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[AnalysisWorkflow, RefinementWorkflow],
        activities=[detect_emotion_activity, generate_scenario_activity, notify_activity],
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
