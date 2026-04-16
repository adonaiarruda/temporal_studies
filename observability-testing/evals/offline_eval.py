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

import json

from braintrust import Eval
from evals.task import classify_and_answer
from src.llm_client import call_llm


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


# ── LLM-as-a-judge scorers via Bedrock ───────────────────────────────────────

async def factuality(input: str, output, expected: str = None, **kwargs) -> float:
    """Judges if the answer is factually equivalent to the expected answer."""
    if not expected:
        return None
    answer = output.get("answer", "") if isinstance(output, dict) else str(output)
    prompt = (
        f"Question: {input}\n"
        f"Expected answer: {expected}\n"
        f"Actual answer: {answer}\n\n"
        "Is the actual answer factually correct and equivalent to the expected answer? "
        "Respond with ONLY JSON: {\"score\": 0.0-1.0, \"reason\": \"...\"}"
    )
    raw = await call_llm(
        system="You are an impartial evaluator. Rate answer correctness from 0.0 (wrong) to 1.0 (correct).",
        user=prompt,
        max_tokens=128,
    )
    try:
        return float(json.loads(raw)["score"])
    except Exception:
        return None


async def relevance(input: str, output, **kwargs) -> float:
    """Judges if the answer is relevant and on-topic for the question."""
    answer = output.get("answer", "") if isinstance(output, dict) else str(output)
    prompt = (
        f"Question: {input}\n"
        f"Answer: {answer}\n\n"
        "Is this answer relevant and on-topic for the question? "
        "Respond with ONLY JSON: {\"score\": 0.0-1.0, \"reason\": \"...\"}"
    )
    raw = await call_llm(
        system="You are an impartial evaluator. Rate answer relevance from 0.0 (irrelevant) to 1.0 (highly relevant).",
        user=prompt,
        max_tokens=128,
    )
    try:
        return float(json.loads(raw)["score"])
    except Exception:
        return None


# ── Task wrapper ──────────────────────────────────────────────────────────────

async def task(question: str) -> dict:
    """Thin async wrapper so Eval() can call classify_and_answer."""
    return await classify_and_answer(question)


# ── Eval() ───────────────────────────────────────────────────────────────────
# Runs the full evaluation. Each invocation creates a new Experiment in
# Braintrust so you can compare results across model versions or prompt changes.

if __name__ == "__main__":
    Eval(
        os.environ.get("BRAINTRUST_PROJECT", "observability-demo"),
        experiment_name="qa-pipeline-eval",
        data=DATASET,
        task=task,
        scores=[
            factuality,       # LLM-as-judge via Bedrock: resposta é factualmente correta?
            relevance,        # LLM-as-judge via Bedrock: resposta é relevante para a pergunta?
            intent_accuracy,  # Exact match: intent classificado corretamente?
        ],
        metadata={
            "model": os.environ.get("LLM_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0"),
            "pipeline": "classify → answer",
        },
    )
