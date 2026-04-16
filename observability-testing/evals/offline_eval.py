"""
Offline evaluation with Braintrust Eval().

Run:
    uv run braintrust run evals/offline_eval.py
  OR (without the CLI):
    uv run python evals/offline_eval.py

What happens:
  1. For each test case in DATASET, `task()` is called
  2. Output is scored by multiple scorers
  3. Results are uploaded to Braintrust → visible under Experiments tab
  4. Compare experiments over time to detect regressions

Scorers used:
  - Factuality    : LLM-as-judge — does the answer match the expected output?
  - IntentAccuracy: Custom — did the classifier predict the right intent?
  - Relevance     : LLM-as-judge (ClosedQA) — is the answer on-topic?
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from braintrust import Eval
from autoevals.llm import Factuality, ClosedQA
from evals.task import classify_and_answer


# ── Dataset ──────────────────────────────────────────────────────────────────
# Each item:
#   input    — the user question passed to task()
#   expected — gold answer used by Factuality scorer
#   metadata — extra info (intent ground truth for IntentAccuracy scorer)
DATASET = [
    {
        "input": "What is the capital of France?",
        "expected": "Paris",
        "metadata": {"expected_intent": "FACTUAL"},
    },
    {
        "input": "What is 15% of 240?",
        "expected": "36",
        "metadata": {"expected_intent": "CALCULATION"},
    },
    {
        "input": "What is machine learning?",
        "expected": (
            "Machine learning is a subset of artificial intelligence where systems "
            "learn from data to improve performance without being explicitly programmed."
        ),
        "metadata": {"expected_intent": "DEFINITION"},
    },
    {
        "input": "How do I reverse a string in Python?",
        "expected": "Use slicing: s[::-1]  or  ''.join(reversed(s))",
        "metadata": {"expected_intent": "PROCEDURAL"},
    },
    {
        "input": "What year did the Berlin Wall fall?",
        "expected": "1989",
        "metadata": {"expected_intent": "FACTUAL"},
    },
    {
        "input": "What is the speed of light?",
        "expected": "299,792,458 meters per second (approximately 3 × 10^8 m/s)",
        "metadata": {"expected_intent": "FACTUAL"},
    },
    {
        "input": "How do you make pasta?",
        "expected": (
            "Boil salted water, add pasta, cook per package instructions, drain, serve with sauce."
        ),
        "metadata": {"expected_intent": "PROCEDURAL"},
    },
    {
        "input": "What does REST stand for in web APIs?",
        "expected": "Representational State Transfer",
        "metadata": {"expected_intent": "DEFINITION"},
    },
    {
        "input": "If a rectangle has sides 8cm and 5cm, what is its area?",
        "expected": "40 cm²",
        "metadata": {"expected_intent": "CALCULATION"},
    },
    {
        "input": "How do I center a div in CSS?",
        "expected": (
            "Use flexbox: set the parent to `display: flex; justify-content: center; align-items: center;`"
        ),
        "metadata": {"expected_intent": "PROCEDURAL"},
    },
]


# ── Custom scorer: intent classification accuracy ────────────────────────────

def intent_accuracy(output: dict, input: str, expected: str, metadata: dict = None) -> float:
    """
    Returns 1.0 if the model's predicted intent matches the expected intent,
    0.0 otherwise. Requires `metadata.expected_intent` to be set.
    """
    if not metadata or "expected_intent" not in metadata:
        return None  # no ground truth — skip
    predicted = (output or {}).get("intent", "")
    return 1.0 if predicted == metadata["expected_intent"] else 0.0


# ── Task wrapper ──────────────────────────────────────────────────────────────

async def task(question: str) -> dict:
    """Thin async wrapper so Eval() can call classify_and_answer."""
    return await classify_and_answer(question)


# ── Eval() ───────────────────────────────────────────────────────────────────
# Runs the full evaluation. Each invocation creates a new Experiment in
# Braintrust so you can compare results across model versions or prompt changes.

Eval(
    "qa-pipeline-eval",
    project_name=os.environ.get("BRAINTRUST_PROJECT", "observability-demo"),
    data=lambda: DATASET,
    task=task,
    scores=[
        Factuality,       # LLM-as-judge: does the answer match `expected`?
        intent_accuracy,  # Exact match: was the intent classified correctly?
        ClosedQA,         # LLM-as-judge: is the answer relevant to the question?
    ],
    metadata={
        "model": os.environ.get("LLM_MODEL", "claude-3-5-haiku-20241022"),
        "pipeline": "classify → answer",
    },
)
