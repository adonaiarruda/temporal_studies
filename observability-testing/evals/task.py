"""
Pure-Python task function for offline evaluation.

This re-implements the QA pipeline logic without Temporal so that Eval()
can call it directly in a batch loop. The LLM calls still go through
the Braintrust proxy, so each eval run gets LLM spans logged.

Reuses prompts from src/prompts.py to stay in sync with the live workflow.
"""
import json
import sys
import os

# Allow running from the project root: `uv run braintrust run evals/offline_eval.py`
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.llm_client import call_llm
from src.prompts import CLASSIFY_SYSTEM, ANSWER_SYSTEM


async def classify_and_answer(question: str) -> dict:
    """
    Full QA pipeline without Temporal context.

    Returns:
        {
            "intent":     str,    # classified intent
            "confidence": float,  # model confidence (0-1)
            "answer":     str,    # generated answer
        }
    """
    # Step 1 — classify intent
    raw = await call_llm(system=CLASSIFY_SYSTEM, user=question, max_tokens=128)
    try:
        classification = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        classification = {"intent": "FACTUAL", "confidence": 0.5, "reason": "parse error"}

    intent = classification.get("intent", "FACTUAL")

    # Step 2 — generate tailored answer
    system = ANSWER_SYSTEM.get(intent, ANSWER_SYSTEM["DEFAULT"])
    answer = await call_llm(system=system, user=question, max_tokens=512)

    return {
        "intent": intent,
        "confidence": classification.get("confidence", 0.5),
        "answer": answer,
    }
