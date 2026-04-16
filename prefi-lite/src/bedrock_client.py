import asyncio
import json
import logging
import os

import boto3
from braintrust import current_span, traced
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

MODEL = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-3-5-sonnet-20241022-v2:0")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

_bedrock = boto3.client(
    "bedrock-runtime",
    region_name=AWS_REGION,
)


@traced(type="llm", name="Bedrock Claude", notrace_io=True)
def _invoke_sync(prompt: str, max_tokens: int) -> str:
    """Chamada síncrona ao Bedrock — executada em thread pool via asyncio.to_thread."""
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
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
        input=[{"role": "user", "content": prompt}],
        output=text,
        metadata={"model": MODEL},
        metrics=dict(
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            tokens=input_tokens + output_tokens,
        ),
    )

    return text


async def invoke_model(prompt: str, max_tokens: int = 2048) -> str:
    """Async wrapper — envolve a chamada síncrona do boto3 para não bloquear o event loop."""
    try:
        return await asyncio.to_thread(_invoke_sync, prompt, max_tokens)
    except Exception as exc:
        raise RuntimeError(
            f"Bedrock call failed. model='{MODEL}', region='{AWS_REGION}'. "
            f"Error: {exc}"
        ) from exc
