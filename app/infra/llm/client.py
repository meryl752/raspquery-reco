"""Façade LLM — Cerebras (Qwen 235B) puis Groq, aligné stackai/lib/llm/router.ts."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel

from app.core.config import Settings
from app.core.models import PreferredModel
from app.infra.llm.cerebras import CerebrasClient
from app.infra.llm.groq import DEFAULT_GROQ_FALLBACK, DEFAULT_GROQ_MODEL, GroqClient

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_PREFERRED_TO_GROQ: dict[str, str] = {
    "qwen-32b": DEFAULT_GROQ_MODEL,
    "llama-70b": DEFAULT_GROQ_FALLBACK,
}


class LlmNotConfiguredError(RuntimeError):
    pass


@dataclass
class LlmClient:
    provider: str
    cerebras: CerebrasClient | None = None
    groq: GroqClient | None = None

    def _resolve_cerebras_model(self, preferred: PreferredModel | None) -> str | None:
        if not self.cerebras:
            return None
        if preferred == "gpt-120b":
            return self.cerebras.fallback_model
        if preferred in ("qwen-235b", None):
            return self.cerebras.primary_model
        return None

    def _resolve_groq_model(self, preferred: PreferredModel | None) -> str | None:
        if not self.groq:
            return None
        if preferred and preferred in _PREFERRED_TO_GROQ:
            return _PREFERRED_TO_GROQ[preferred]
        return None

    async def _call_cerebras_chain(
        self,
        output_model: type[T],
        user_prompt: str,
        *,
        system_prompt: str,
        max_tokens: int,
        schema_name: str,
        preferred_model: PreferredModel | None,
        known_task_ids: list[str] | None,
        prefer_json_object: bool = False,
    ) -> T:
        if not self.cerebras:
            raise LlmNotConfiguredError("Cerebras non configuré")
        model = self._resolve_cerebras_model(preferred_model)
        if model is None:
            raise LlmNotConfiguredError(f"Cerebras incompatible avec preferred={preferred_model}")
        return await self.cerebras.complete_structured(
            output_model,
            user_prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            schema_name=schema_name,
            model=model,
            known_task_ids=known_task_ids,
            prefer_json_object=prefer_json_object,
        )

    async def _call_groq_chain(
        self,
        output_model: type[T],
        user_prompt: str,
        *,
        system_prompt: str,
        max_tokens: int,
        schema_name: str,
        preferred_model: PreferredModel | None,
        known_task_ids: list[str] | None,
        prefer_json_object: bool = False,
    ) -> T:
        if not self.groq:
            raise LlmNotConfiguredError("Groq non configuré")
        model = self._resolve_groq_model(preferred_model)
        return await self.groq.complete_structured(
            output_model,
            user_prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            schema_name=schema_name,
            model=model,
            known_task_ids=known_task_ids,
            prefer_json_object=prefer_json_object,
        )

    async def complete_structured(
        self,
        output_model: type[T],
        user_prompt: str,
        *,
        system_prompt: str = "",
        max_tokens: int = 1024,
        schema_name: str = "structured_output",
        preferred_model: PreferredModel | None = None,
        known_task_ids: list[str] | None = None,
        prefer_json_object: bool = False,
    ) -> T:
        """
        Chaîne par défaut (qwen-235b / None) : Cerebras (235B + fallback interne) → Groq.
        Préférences Groq (qwen-32b, llama-70b) : Groq uniquement.
        """
        errors: list[str] = []
        kwargs = dict(
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            schema_name=schema_name,
            known_task_ids=known_task_ids,
            prefer_json_object=prefer_json_object,
        )

        groq_only = preferred_model in ("qwen-32b", "llama-70b")
        cerebras_first = preferred_model in (None, "qwen-235b", "gpt-120b")

        if groq_only and self.groq:
            try:
                return await self._call_groq_chain(
                    output_model,
                    user_prompt,
                    preferred_model=preferred_model,
                    **kwargs,
                )
            except Exception as exc:
                raise LlmNotConfiguredError(f"groq: {exc}") from exc

        if cerebras_first and self.cerebras:
            try:
                return await self._call_cerebras_chain(
                    output_model,
                    user_prompt,
                    preferred_model=preferred_model,
                    **kwargs,
                )
            except Exception as exc:
                errors.append(f"cerebras: {exc}")
                logger.warning(
                    "Chaîne Cerebras échouée pour %s — bascule Groq si disponible: %s",
                    schema_name,
                    exc,
                )

        if self.groq:
            try:
                return await self._call_groq_chain(
                    output_model,
                    user_prompt,
                    preferred_model=preferred_model if groq_only else None,
                    **kwargs,
                )
            except Exception as exc:
                errors.append(f"groq: {exc}")

        raise LlmNotConfiguredError("; ".join(errors) or "Aucun fournisseur LLM")


def create_llm_client(settings: Settings) -> LlmClient | None:
    cerebras = None
    groq = None

    if settings.cerebras_api_key:
        cerebras = CerebrasClient(
            api_key=settings.cerebras_api_key,
            primary_model=settings.cerebras_model,
            fallback_model=settings.cerebras_model_fallback,
        )
    if settings.groq_api_key:
        groq = GroqClient(
            api_key=settings.groq_api_key,
            primary_model=settings.groq_model,
            fallback_model=settings.groq_model_fallback,
        )

    if not cerebras and not groq:
        return None

    provider = "cerebras" if cerebras else "groq"
    return LlmClient(provider=provider, cerebras=cerebras, groq=groq)
