import copy
import json
import os

from dotenv import load_dotenv
from openai import OpenAI

from . import db

load_dotenv()

MODEL = os.getenv("OPENAI_MODEL", "gpt-5.6-sol")
INPUT_PRICE = float(os.getenv("OPENAI_INPUT_PRICE_PER_MILLION", "4.0"))
OUTPUT_PRICE = float(os.getenv("OPENAI_OUTPUT_PRICE_PER_MILLION", "20.0"))

client = OpenAI() if os.getenv("OPENAI_API_KEY") else None


def usage_cost(response):
    """Return input tokens, output tokens, reasoning tokens, and estimated cost."""
    usage = response.usage
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)

    details = getattr(usage, "output_tokens_details", None)
    reasoning_tokens = (
        int(getattr(details, "reasoning_tokens", 0) or 0)
        if details
        else 0
    )

    # Reasoning tokens are already included in output_tokens.
    cost = (
        input_tokens / 1_000_000 * INPUT_PRICE
        + output_tokens / 1_000_000 * OUTPUT_PRICE
    )
    return input_tokens, output_tokens, reasoning_tokens, cost


def make_strict_schema(schema):
    """
    Normalize a Pydantic-generated JSON Schema for OpenAI strict structured output.
    Every object disallows extra properties and requires all declared properties.
    """
    schema = copy.deepcopy(schema)

    def normalize(node):
        if isinstance(node, dict):
            properties = node.get("properties")
            if node.get("type") == "object" or properties is not None:
                properties = properties or {}
                node["additionalProperties"] = False
                node["required"] = list(properties.keys())

            for value in node.values():
                normalize(value)
        elif isinstance(node, list):
            for item in node:
                normalize(item)

    normalize(schema)
    return schema


def text_call(prompt, story_id, node, episode_number=None):
    if client is None:
        raise RuntimeError(
            "OPENAI_API_KEY is missing. Add your API key to the project's .env file."
        )

    response = client.responses.create(model=MODEL, input=prompt)
    usage = usage_cost(response)
    db.log_usage(story_id, episode_number, node, MODEL, *usage)
    return response.output_text


def structured_call(
    prompt,
    schema,
    schema_name,
    story_id,
    node,
    episode_number=None,
):
    if client is None:
        raise RuntimeError(
            "OPENAI_API_KEY is missing. Add your API key to the project's .env file."
        )

    json_schema = make_strict_schema(schema.model_json_schema())

    response = client.responses.create(
        model=MODEL,
        input=prompt,
        text={
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": json_schema,
            }
        },
    )

    usage = usage_cost(response)
    db.log_usage(story_id, episode_number, node, MODEL, *usage)

    output_text = getattr(response, "output_text", None)
    if not output_text:
        raise RuntimeError("The model returned no structured output.")

    try:
        return schema.model_validate(json.loads(output_text))
    except Exception as exc:
        raise RuntimeError(
            f"Could not validate structured output for '{schema_name}': {exc}"
        ) from exc
