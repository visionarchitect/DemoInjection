import json

import pytest
from pydantic import ValidationError

from app.agent.schemas import PRODUCT_JSON_SCHEMA, Product, product_from_output


def test_product_schema_accepts_catalogue_record():
    product = Product(id="p-1", name="Demo Sensor", manufacturer="Fictional Co", category="Sensor", short_description="Short", long_description="Long", features=["one"], technical_specs={"range": "0-10"}, tags=["demo"])
    assert product.id == "p-1"


def test_product_schema_rejects_missing_required_data():
    with pytest.raises(ValidationError):
        Product.model_validate({"id": "p-1", "name": "Incomplete"})


def test_strict_schema_is_openai_compatible():
    # Every object in the model-facing schema must enumerate its keys in
    # `required` and set `additionalProperties` to false, and must not leak a
    # free-form dict into any object definition.
    def check(node):
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False
                props = set(node.get("properties", {}))
                assert set(node.get("required", [])) == props
            for value in node.values():
                check(value)
        elif isinstance(node, list):
            for value in node:
                check(value)

    check(PRODUCT_JSON_SCHEMA)


def test_product_from_output_normalizes_array_specs():
    payload = {
        "id": "p-1",
        "name": "Demo Sensor",
        "manufacturer": "Fictional Co",
        "category": "Sensor",
        "short_description": "Short",
        "long_description": "Long",
        "features": ["one"],
        "technical_specs": [{"key": "range", "value": "0-10"}],
        "tags": ["demo"],
    }
    product = product_from_output(json.dumps(payload))
    assert product.technical_specs == {"range": "0-10"}


def test_product_from_output_accepts_dict_specs():
    payload = {
        "id": "p-1",
        "name": "Demo Sensor",
        "manufacturer": "Fictional Co",
        "category": "Sensor",
        "short_description": "Short",
        "long_description": "Long",
        "features": ["one"],
        "technical_specs": {"range": "0-10"},
        "tags": ["demo"],
    }
    product = product_from_output(json.dumps(payload))
    assert product.technical_specs == {"range": "0-10"}
