"""
Activity: answer_question_activity

Generates an answer tailored to the question's intent.
The system prompt is chosen based on the classified intent so the model
adapts its tone (precise for FACTUAL, step-by-step for PROCEDURAL, etc.).
"""
from temporalio import activity
from src.llm_client import call_llm
from src.prompts import ANSWER_SYSTEM


@activity.defn(name="answer_question_activity")
async def answer_question(input: dict) -> str:
    """
    input: {"question": str, "intent": str}
    Returns: answer text
    """
    question = input["question"]
    intent = input.get("intent", "DEFAULT")

    system = ANSWER_SYSTEM.get(intent, ANSWER_SYSTEM["DEFAULT"])
    answer = await call_llm(system=system, user=question, max_tokens=512)

    activity.logger.info(
        "generated answer",
        extra={"intent": intent, "answer_length": len(answer)},
    )
    return answer
