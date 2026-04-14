import json
from pathlib import Path
from temporalio import activity
from langsmith import traceable
from src.bedrock_client import invoke_model

_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "emotion_detection.txt"


@activity.defn(name="detect_emotion_activity")
@traceable(run_type="chain", name="detect-emotion")
async def detect_emotion_activity(mensagem: str) -> dict:
    template = _PROMPT_PATH.read_text(encoding="utf-8")
    prompt = template.replace("{mensagem}", mensagem)

    raw = invoke_model(prompt)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: extrai o primeiro bloco JSON da resposta
        import re
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            raise ValueError(f"Bedrock returned non-JSON response: {raw[:200]}")
        result = json.loads(match.group())

    estado = result.get("estado", "").upper()
    valid_states = {"ANSIOSO", "CONFUSO", "CONFIANTE", "FRUSTRADO"}
    if estado not in valid_states:
        raise ValueError(f"Invalid emotional state: {estado!r}")

    return {
        "estado": estado,
        "confianca": float(result.get("confianca", 0.0)),
        "justificativa": result.get("justificativa", ""),
    }
