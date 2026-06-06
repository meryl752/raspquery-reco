"""Embeddings Jina v3 (1024 dims) — même fournisseur que le monolithe Next."""

import time

import httpx

from app.core.config import Settings


class EmbeddingsNotConfiguredError(RuntimeError):
    pass


async def generate_embedding(settings: Settings, text: str) -> tuple[list[float], int]:
    if not settings.jina_api_key:
        raise EmbeddingsNotConfiguredError("JINA_API_KEY manquant")

    start = time.perf_counter()
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.jina.ai/v1/embeddings",
            headers={
                "Authorization": f"Bearer {settings.jina_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.jina_embedding_model,
                "task": "retrieval.query",
                "input": [text],
            },
        )
        response.raise_for_status()
        data = response.json()
        vector = data["data"][0]["embedding"]

    latency_ms = int((time.perf_counter() - start) * 1000)
    return vector, latency_ms
