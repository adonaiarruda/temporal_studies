import asyncio
import logging
import os
from dotenv import load_dotenv
from temporalio.client import Client
from temporalio.worker import Worker

from src.workflows.analysis_workflow import AnalysisWorkflow
from src.workflows.refinement_workflow import RefinementWorkflow
from src.activities.emotion_detection import detect_emotion_activity
from src.activities.scenario_generation import generate_scenario_activity
from src.activities.notification import notify_activity

load_dotenv()
logging.basicConfig(level=logging.INFO)


async def main():
    client = await Client.connect(
        os.environ.get("TEMPORAL_HOST", "localhost:7233")
    )
    task_queue = os.environ.get("TEMPORAL_TASK_QUEUE", "prefi-lite")

    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=[AnalysisWorkflow, RefinementWorkflow],
        activities=[detect_emotion_activity, generate_scenario_activity, notify_activity],
    )

    logging.info("Worker started on task queue: %s", task_queue)
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
