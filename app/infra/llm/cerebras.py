"""Client Cerebras — Qwen 3 235B (aligné stackai/lib/cerebras/client.ts)."""

from __future__ import annotations

import json
import logging
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.infra.llm.coerce import validate_llm_model
from app.infra.llm.parse import parse_llm_json, strip_llm_wrapper
from app.infra.llm.retry import with_provider_retries
from app.infra.llm.schema import build_groq_response_format, model_supports_json_schema

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

CEREBRAS_CHAT_URL = "https://api.cerebras.ai/v1/chat/completions"

# stackai/lib/cerebras/client.ts
DEFAULT_CEREBRAS_MODEL = "qwen-3-235b-a22b-instruct-2507"
DEFAULT_CEREBRAS_FALLBACK = "gpt-oss-120b"

CALL_TIMEOUT_SHORT_S = 15.0
CALL_TIMEOUT_LONG_S = 45.0
PROVIDER_MAX_ATTEMPTS = 4


class CerebrasApiError(RuntimeError):
    pass


class CerebrasClient:
    def __init__(
        self,
        api_key: str,
        primary_model: str = DEFAULT_CEREBRAS_MODEL,
        fallback_model: str = DEFAULT_CEREBRAS_FALLBACK,
    ) -> None:
        self.api_key = api_key
        self.primary_model = primary_model
        self.fallback_model = fallback_model

    def _timeout_for(self, max_tokens: int) -> float:
        return CALL_TIMEOUT_LONG_S if max_tokens > 1500 else CALL_TIMEOUT_SHORT_S

    async def _chat_completion(
        self,
        *,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int,
        response_format: dict | None,
    ) -> str:
        payload: dict = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }
        if response_format:
            payload["response_format"] = response_format

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async def _post_once() -> httpx.Response:
            async with httpx.AsyncClient(timeout=self._timeout_for(max_tokens)) as client:
                return await client.post(CEREBRAS_CHAT_URL, headers=headers, json=payload)

        response = await with_provider_retries(
            f"Cerebras {model}",
            _post_once,
            max_attempts=PROVIDER_MAX_ATTEMPTS,
        )

        if response.status_code >= 400:
            raise CerebrasApiError(
                f"Cerebras HTTP {response.status_code}: {response.text[:500]}"
            )

        data = response.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content") or ""
        return strip_llm_wrapper(content)

    async def complete_structured(
        self,
        output_model: type[T],
        user_prompt: str,
        *,
        system_prompt: str = "",
        max_tokens: int = 1024,
        schema_name: str = "structured_output",
        model: str | None = None,
        known_task_ids: list[str] | None = None,
        prefer_json_object: bool = False,
    ) -> T:
        models_to_try = [model or self.primary_model, self.fallback_model]
        models_to_try = list(dict.fromkeys(m for m in models_to_try if m))

        last_error: Exception | None = None
        for model_id in models_to_try:
            use_schema = (
                not prefer_json_object and model_supports_json_schema(model_id)
            )
            response_format = build_groq_response_format(
                output_model,
                schema_name,
                strict=False,
                use_json_schema=use_schema,
            )
            sys = system_prompt or (
                "Tu réponds uniquement en JSON valide conforme au schéma demandé."
            )
            if response_format.get("type") == "json_object":
                sys += (
                    " Format: JSON object. Utilise EXACTEMENT les clés anglaises demandées "
                    "(ex: subtasks, pas tasks)."
                )
            messages = [
                {"role": "system", "content": sys},
                {"role": "user", "content": user_prompt},
            ]

            try:
                raw = await self._chat_completion(
                    model=model_id,
                    messages=messages,
                    max_tokens=max_tokens,
                    response_format=response_format,
                )
                parsed = parse_llm_json(raw)
                result = validate_llm_model(
                    parsed, output_model, known_task_ids=known_task_ids
                )
                logger.info(
                    "cerebras structured ok model=%s schema=%s json_schema=%s",
                    model_id,
                    schema_name,
                    use_schema,
                )
                return result
            except CerebrasApiError as exc:
                last_error = exc
                logger.warning("cerebras structured failed model=%s: %s", model_id, exc)
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                last_error = exc
                logger.warning(
                    "cerebras structured failed model=%s: %s",
                    model_id,
                    exc,
                )

        raise CerebrasApiError(
            f"Tous les modèles Cerebras ont échoué pour {schema_name}: {last_error}"
        )
