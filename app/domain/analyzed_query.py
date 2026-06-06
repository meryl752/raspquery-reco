"""
Modèle strict de l'analyse de requête — remplace le JSON.parse + filtre manuel TS.

Aligné sur stackai/lib/constants.ts (pas de catégories inventées type CRM/scraping).
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Self

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.constants import VALID_CATEGORIES


class ValidCategory(str, Enum):
    COPYWRITING = "copywriting"
    IMAGE = "image"
    AUTOMATION = "automation"
    ANALYTICS = "analytics"
    CUSTOMER_SERVICE = "customer_service"
    SEO = "seo"
    PROSPECTING = "prospecting"
    CODING = "coding"
    RESEARCH = "research"
    VIDEO = "video"
    WEBSITE = "website"

    @classmethod
    def values(cls) -> list[str]:
        return [c.value for c in cls]


class AtomicSubtask(BaseModel):
    """Sous-tâche atomique avec catégorie obligatoire et graphe de dépendances."""

    id: str = Field(..., min_length=1, pattern=r"^[a-zA-Z0-9_-]+$")
    action: str = Field(..., min_length=1)
    required_category: ValidCategory
    depends_on: list[str] = Field(default_factory=list)
    can_be_automated: bool = True

    @field_validator("depends_on")
    @classmethod
    def strip_dep_ids(cls, v: list[str]) -> list[str]:
        return [x.strip() for x in v if x and x.strip()]


class FunctionalDomain(BaseModel):
    name: str = Field(..., min_length=1)
    priority: int = Field(..., ge=1)
    subtasks: list[AtomicSubtask] = Field(..., min_length=1)


class AnalyzedQuery(BaseModel):
    """
    Sortie canonique du query analyzer.
    `required_categories` et `subtasks` (texte plat) sont toujours dérivés — jamais vides après validation.
    """

    original: str = Field(..., min_length=1)
    domains: list[FunctionalDomain] = Field(..., min_length=1)
    implicit_constraints: list[str] = Field(default_factory=list)
    sector_context: str = ""
    budget_max: int = Field(..., ge=0)
    subtasks: list[str] = Field(default_factory=list)
    required_categories: list[ValidCategory] = Field(default_factory=list)

    @model_validator(mode="after")
    def derive_flat_fields(self) -> Self:
        flat_actions: list[str] = []
        categories: set[ValidCategory] = set()
        all_ids: set[str] = set()

        for domain in self.domains:
            for st in domain.subtasks:
                if st.id in all_ids:
                    raise ValueError(f"Duplicate subtask id: {st.id}")
                all_ids.add(st.id)
                flat_actions.append(st.action)
                categories.add(st.required_category)

        for domain in self.domains:
            for st in domain.subtasks:
                for dep in st.depends_on:
                    if dep not in all_ids:
                        raise ValueError(
                            f"Subtask {st.id} depends on unknown id {dep}"
                        )
                    if dep == st.id:
                        raise ValueError(f"Subtask {st.id} cannot depend on itself")

        if not categories:
            raise ValueError("required_categories cannot be empty")

        self.subtasks = flat_actions
        self.required_categories = sorted(categories, key=lambda c: c.value)
        return self

    @property
    def required_category_values(self) -> list[str]:
        return [c.value for c in self.required_categories]

    @classmethod
    def category_list_for_prompt(cls) -> str:
        return ", ".join(VALID_CATEGORIES)


# ─── Schémas de sortie LLM (structured output / validation post-parse) ───────


class LlmSubtaskRow(BaseModel):
    """Une ligne renvoyée par le LLM — validée avant fusion dans AnalyzedQuery."""

    id: str = Field(..., pattern=r"^[a-zA-Z0-9_-]+$")
    action: str = Field(..., min_length=1)
    required_category: ValidCategory
    depends_on: list[str] = Field(default_factory=list)
    can_be_automated: bool = True


class QueryAnalyzerPass1Output(BaseModel):
    """Passe 1 : décomposition avec catégories strictes et dépendances optionnelles."""

    subtasks: list[LlmSubtaskRow] = Field(..., min_length=1)
    sector_context: str = ""
    implicit_constraints: list[str] = Field(default_factory=list)

    def to_analyzed_query(self, original: str, budget_max: int) -> AnalyzedQuery:
        atomic = [
            AtomicSubtask(
                id=row.id,
                action=row.action,
                required_category=row.required_category,
                depends_on=row.depends_on,
                can_be_automated=row.can_be_automated,
            )
            for row in self.subtasks
        ]
        return AnalyzedQuery(
            original=original,
            domains=[
                FunctionalDomain(
                    name="Plan principal",
                    priority=1,
                    subtasks=atomic,
                )
            ],
            implicit_constraints=self.implicit_constraints,
            sector_context=self.sector_context or "",
            budget_max=budget_max,
        )


class DomainGroupingRow(BaseModel):
    name: str
    priority: int = Field(..., ge=1)
    task_ids: list[str] = Field(..., min_length=1)


class QueryAnalyzerPass2Output(BaseModel):
    domains: list[DomainGroupingRow] = Field(..., min_length=1)

    def apply_to(
        self, base: AnalyzedQuery, subtasks_by_id: dict[str, AtomicSubtask]
    ) -> AnalyzedQuery:
        new_domains: list[FunctionalDomain] = []
        for row in sorted(self.domains, key=lambda d: d.priority):
            sts = [subtasks_by_id[tid] for tid in row.task_ids if tid in subtasks_by_id]
            if sts:
                new_domains.append(
                    FunctionalDomain(
                        name=row.name,
                        priority=row.priority,
                        subtasks=sts,
                    )
                )
        if not new_domains:
            return base
        return AnalyzedQuery(
            original=base.original,
            domains=new_domains,
            implicit_constraints=base.implicit_constraints,
            sector_context=base.sector_context,
            budget_max=base.budget_max,
        )


def coerce_category(value: str) -> ValidCategory | None:
    """Normalise une chaîne LLM vers une catégorie valide."""
    v = value.strip().lower().replace(" ", "_")
    if v in VALID_CATEGORIES:
        return ValidCategory(v)
    # alias fréquents
    aliases = {
        "marketing": ValidCategory.COPYWRITING,
        "content": ValidCategory.COPYWRITING,
        "support": ValidCategory.CUSTOMER_SERVICE,
        "chat": ValidCategory.CUSTOMER_SERVICE,
        "dev": ValidCategory.CODING,
        "code": ValidCategory.CODING,
        "ecommerce": ValidCategory.WEBSITE,
        "shop": ValidCategory.WEBSITE,
    }
    return aliases.get(v)
