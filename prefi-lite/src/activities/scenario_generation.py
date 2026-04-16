from pathlib import Path
from temporalio import activity
from src.bedrock_client import invoke_model

_PROMPT_PATH = Path(__file__).parent.parent.parent / "prompts" / "scenario_generation.txt"


@activity.defn(name="generate_scenario_activity")
async def generate_scenario_activity(params: dict) -> str:
    mensagem: str = params["mensagem"]
    estado: str = params["estado"]
    contexto_anterior: str = params.get("contexto_anterior", "")

    template = _PROMPT_PATH.read_text(encoding="utf-8")
    prompt = (
        template
        .replace("{estado_emocional}", estado)
        .replace("{contexto_anterior}", contexto_anterior)
        .replace("{mensagem}", mensagem)
    )

    return await invoke_model(prompt)
