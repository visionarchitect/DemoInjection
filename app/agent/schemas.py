from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field


class Product(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    manufacturer: str = Field(min_length=1)
    category: str = Field(min_length=1)
    short_description: str = Field(min_length=1)
    long_description: str = Field(min_length=1)
    features: list[str] = Field(min_length=1)
    technical_specs: dict[str, str]
    tags: list[str]


# Schema sent to the model. OpenAI strict structured outputs cannot express a
# free-form `dict[str, str]` (strict mode requires every object to enumerate
# its keys in `required` and set `additionalProperties: false`), so
# `technical_specs` is modeled here as an array of {key, value} pairs and
# converted back to a dict in `product_from_output`.
PRODUCT_JSON_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "id": {"type": "string"},
        "name": {"type": "string"},
        "manufacturer": {"type": "string"},
        "category": {"type": "string"},
        "short_description": {"type": "string"},
        "long_description": {"type": "string"},
        "features": {"type": "array", "items": {"type": "string"}},
        "technical_specs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["key", "value"],
                "additionalProperties": False,
            },
        },
        "tags": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "id",
        "name",
        "manufacturer",
        "category",
        "short_description",
        "long_description",
        "features",
        "technical_specs",
        "tags",
    ],
}


def product_from_output(output: str) -> Product:
    """Parse model output into a Product, normalizing technical_specs to a dict."""
    data = json.loads(output)
    if not isinstance(data, dict):
        raise ValueError("Model output must be a JSON object.")
    specs = data.get("technical_specs")
    if isinstance(specs, list):
        data["technical_specs"] = {
            str(item["key"]): str(item["value"])
            for item in specs
            if isinstance(item, dict) and "key" in item and "value" in item
        }
    elif not isinstance(specs, dict):
        data["technical_specs"] = {}
    return Product.model_validate(data)
