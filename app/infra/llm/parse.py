"""Parse et validation JSON LLM → modèles Pydantic."""

from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

_FENCE_START = re.compile(r"^```(?:json)?\s*", re.I)
_FENCE_END = re.compile(r"\s*```$")
_JSON_OBJECT_RE = re.compile(r"\{[\s\S]*\}")
# Séquences \u invalides fréquentes dans les sorties Qwen (JSON tronqué)
_INVALID_U_ESCAPE = re.compile(r"\\u(?![0-9a-fA-F]{4})")


def repair_json_text(text: str) -> str:
    """Corrige les échappements Unicode invalides avant json.loads."""
    t = strip_llm_wrapper(text)
    if _INVALID_U_ESCAPE.search(t):
        t = _INVALID_U_ESCAPE.sub(r"\\\\u", t)
    return t


def strip_llm_wrapper(text: str) -> str:
    t = text.strip()
    # Retire les balises markdown et extrait le premier objet JSON
    t = _FENCE_START.sub("", t)
    t = _FENCE_END.sub("", t)
    t = t.strip()
    if not t.startswith("{"):
        match = _JSON_OBJECT_RE.search(t)
        if match:
            t = match.group(0)
    return t


def parse_llm_json(text: str) -> dict | list:
    cleaned = repair_json_text(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Dernier recours : extrait le premier objet { ... } équilibré grossièrement
        start = cleaned.find("{")
        if start < 0:
            raise
        depth = 0
        for i in range(start, len(cleaned)):
            if cleaned[i] == "{":
                depth += 1
            elif cleaned[i] == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(cleaned[start : i + 1])
        raise


def validate_llm_output(text: str, model: type[T]) -> T:
    raw = parse_llm_json(text)
    return model.model_validate(raw)


def validate_llm_output_safe(text: str, model: type[T]) -> T | None:
    try:
        return validate_llm_output(text, model)
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
        return None


def pydantic_json_schema(model: type[BaseModel]) -> dict:
    """Schéma pour response_format / structured outputs (OpenAI-compatible)."""
    return model.model_json_schema()
