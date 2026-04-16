"""
LLM client — boto3 apontando diretamente para AWS Bedrock.

Por que essa abordagem:
- Chamadas diretas ao Bedrock via boto3, sem proxy intermediário.
- asyncio.to_thread envolve a chamada síncrona do boto3 para não bloquear o event loop.
- max_retries=0 (implícito): o RetryPolicy do Temporal controla as retentativas.

Observabilidade no Braintrust:
- Spans de Workflow e Activity são registrados automaticamente pelo BraintrustPlugin (worker.py).
- Sub-spans de LLM (tokens, custo) não são capturados automaticamente — boto3 não expõe
  os dados no formato do proxy Braintrust. A latência no nível de Activity ainda é visível.
"""
import asyncio
import json
import logging
import os

import boto3
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

MODEL = os.environ.get("LLM_MODEL", "us.anthropic.claude-3-5-haiku-20241022-v1:0")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

_bedrock = boto3.client(
    "bedrock-runtime",
    region_name=AWS_REGION,
)


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
    return result["content"][0]["text"]


async def call_llm(system: str, user: str, max_tokens: int = 512) -> str:
    """Única chamada LLM. Retorna texto puro."""
    try:
        return await asyncio.to_thread(_invoke_sync, system, user, max_tokens)
    except Exception as exc:
        raise RuntimeError(
            f"Bedrock call failed. model='{MODEL}', region='{AWS_REGION}'. "
            f"Error: {exc}"
        ) from exc
