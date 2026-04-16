"""
QAWorkflow — Question & Answer pipeline

Two sequential activities:
  1. classify_question_activity → detects intent (FACTUAL, PROCEDURAL, etc.)
  2. answer_question_activity   → generates a tailored answer

Braintrust trace hierarchy (via BraintrustPlugin):
  QAWorkflow [task span]
    ├── classify_question_activity [task span]
    │     └── POST /v1/proxy (LLM call) [llm span — tokens, cost, latency]
    └── answer_question_activity [task span]
          └── POST /v1/proxy (LLM call) [llm span — tokens, cost, latency]
"""
from dataclasses import dataclass
from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy


@dataclass
class QAInput:
    question: str


@dataclass
class QAResult:
    question: str
    intent: str
    confidence: float
    answer: str


_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_attempts=3,
)
_TIMEOUT = timedelta(minutes=2)


@workflow.defn
class QAWorkflow:

    @workflow.run
    async def run(self, input: QAInput) -> QAResult:
        # Step 1 — classify intent
        classification: dict = await workflow.execute_activity(
            "classify_question_activity",
            input.question,
            schedule_to_close_timeout=_TIMEOUT,
            retry_policy=_RETRY,
        )

        # Step 2 — generate answer adapted to that intent
        answer: str = await workflow.execute_activity(
            "answer_question_activity",
            {"question": input.question, "intent": classification["intent"]},
            schedule_to_close_timeout=_TIMEOUT,
            retry_policy=_RETRY,
        )

        return QAResult(
            question=input.question,
            intent=classification["intent"],
            confidence=classification.get("confidence", 0.0),
            answer=answer,
        )
