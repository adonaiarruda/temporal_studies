"""
LLM client — boto3 apontando diretamente para AWS Bedrock.

Por que essa abordagem:
- Chamadas diretas ao Bedrock via boto3, sem proxy intermediário.
- asyncio.to_thread envolve a chamada síncrona do boto3 para não bloquear o event loop.
- max_retries=0 (implícito): o RetryPolicy do Temporal controla as retentativas.

Observabilidade no Braintrust:
- @traced(type="llm", notrace_io=True) cria um span LLM sem logar os args da função.
- Tokens (input/output) são extraídos do response do Bedrock e logados manualmente.
- O span aparece aninhado sob o Activity span criado pelo BraintrustPlugin.
"""
import asyncio
import json
import logging
import os

import boto3
from braintrust import current_span, traced
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

MODEL = os.environ.get("LLM_MODEL", "us.anthropic.claude-haiku-4-5-20251001-v1:0")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

_bedrock = boto3.client(
    "bedrock-runtime",
    region_name=AWS_REGION,
)


@traced(type="llm", name="Bedrock Claude", notrace_io=True)
def _invoke_sync(system: str, user: str, max_tokens: int) -> str:
    """Chamada síncrona ao Bedrock — executada em thread pool via asyncio.to_thread."""
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    })
    response = _bedrock.invoke_model(
        modelId=MODEL,
        contentType="application/json",
        accept="application/json",
        body=body,
    )
    result = json.loads(response["body"].read())
    text = result["content"][0]["text"]

    usage = result.get("usage", {})
    input_tokens = usage.get("input_tokens", 0)
    output_tokens = usage.get("output_tokens", 0)

    current_span().log(
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        output=text,
        metadata={"model": MODEL},
        metrics=dict(
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            tokens=input_tokens + output_tokens,
        ),
    )

    return text


async def call_llm(system: str, user: str, max_tokens: int = 512) -> str:
    """Única chamada LLM. Retorna texto puro."""
    try:
        return await asyncio.to_thread(_invoke_sync, system, user, max_tokens)
    except Exception as exc:
        raise RuntimeError(
            f"Bedrock call failed. model='{MODEL}', region='{AWS_REGION}'. "
            f"Error: {exc}"
        ) from exc
