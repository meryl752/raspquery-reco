"""Texte d'embedding retrieval — parité stackai/lib/agents/retrievalText.ts."""

from __future__ import annotations

from app.core.models import UserContext
from app.domain.analyzed_query import AnalyzedQuery


def build_retrieval_embedding_text(ctx: UserContext, query: AnalyzedQuery) -> str:
    parts: list[str] = [
        ctx.objective,
        f"Secteur: {ctx.sector}",
        query.sector_context or "",
        f"Niveau technique: {ctx.tech_level}",
    ]

    if ctx.current_tools:
        tools = ", ".join(ctx.current_tools[:10])
        parts.append(f"Outils déjà utilisés: {tools}")

    if query.implicit_constraints:
        constraints = "; ".join(query.implicit_constraints[:6])
        parts.append(f"Contraintes: {constraints}")

    parts.append(f"Catégories: {', '.join(query.required_category_values)}")
    parts.extend(query.subtasks[:8])

    return ". ".join(p.strip() for p in parts if p and p.strip())
