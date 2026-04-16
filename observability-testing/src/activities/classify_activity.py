"""
Activity: classify_question_activity

Temporal activity that classifies a question into one of 5 intents.
Each call becomes an Activity span in Braintrust (via BraintrustPlugin),
with the nested LLM call logged as a child LLM span automatically.
"""
import json
from temporalio import activity
from src.llm_client import call_llm
from src.prompts import CLASSIFY_SYSTEM


@activity.defn(name="classify_question_activity")
async def classify_question(question: str) -> dict:
    """
    Returns: {"intent": str, "confidence": float, "reason": str}
    """
    raw = await call_llm(system=CLASSIFY_SYSTEM, user=question, max_tokens=128)

    try:
        result = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        # Model returned non-JSON — default gracefully, Temporal will log the raw text
        result = {"intent": "FACTUAL", "confidence": 0.5, "reason": f"parse error: {raw[:80]}"}

    activity.logger.info(
        "classified question",
        extra={
            "question_snippet": question[:60],
            "intent": result.get("intent"),
            "confidence": result.get("confidence"),
        },
    )
    return result
