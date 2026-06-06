"""Préparation des schémas JSON pour Groq structured outputs."""

from __future__ import annotations

import copy
from typing import Any

from pydantic import BaseModel


def _inline_json_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Résout les $ref vers $defs pour les APIs qui n'acceptent pas les refs externes."""
    schema = copy.deepcopy(schema)
    defs = schema.pop("$defs", None) or schema.pop("definitions", None) or {}

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref = node["$ref"]
                if ref.startswith("#/$defs/"):
                    key = ref.split("/")[-1]
                    return resolve(defs.get(key, node))
                if ref.startswith("#/definitions/"):
                    key = ref.split("/")[-1]
                    return resolve(defs.get(key, node))
            return {k: resolve(v) for k, v in node.items()}
        if isinstance(node, list):
            return [resolve(x) for x in node]
        return node

    return resolve(schema)


def build_groq_response_format(
    model: type[BaseModel],
    name: str,
    *,
    strict: bool = False,
    use_json_schema: bool = True,
) -> dict[str, Any]:
    """
    Format response_format Groq.

    - json_schema : modèles Structured Outputs (gpt-oss, llama-4-scout, …)
    - json_object : qwen3-32b, llama-3.3-70b (puis validation Pydantic côté client)
    """
    if use_json_schema:
        raw = model.model_json_schema()
        schema = _inline_json_refs(raw)
        return {
            "type": "json_schema",
            "json_schema": {
                "name": name,
                "strict": strict,
                "schema": schema,
            },
        }
    return {"type": "json_object"}


def model_supports_json_schema(model_id: str) -> bool:
    """Modèles Groq documentés avec json_schema (best-effort ou strict)."""
    supported_prefixes = (
        "openai/gpt-oss",
        "meta-llama/llama-4-scout",
    )
    return any(model_id.startswith(p) for p in supported_prefixes)
