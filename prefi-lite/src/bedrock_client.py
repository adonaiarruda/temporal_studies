import json
import os
import boto3
from botocore.exceptions import ClientError


def get_bedrock_client():
    return boto3.client(
        "bedrock-runtime",
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )


def invoke_model(prompt: str) -> str:
    client = get_bedrock_client()
    model_id = os.environ.get(
        "BEDROCK_MODEL_ID", "us.anthropic.claude-3-5-sonnet-20241022-v2:0"
    )

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2048,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        response = client.invoke_model(
            modelId=model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        return result["content"][0]["text"]
    except ClientError as e:
        raise RuntimeError(f"Bedrock invocation failed: {e}") from e
