"""Constantes métier alignées sur stackai/lib/constants.ts."""

from typing import Literal

BUDGET_MAP: dict[str, int] = {
    "zero": 0,
    "low": 50,
    "medium": 200,
    "high": 1000,
}

DIFFICULTY_ALLOWED: dict[str, list[str]] = {
    "beginner": ["easy"],
    "intermediate": ["easy", "medium"],
    "advanced": ["easy", "medium", "hard"],
}

# Miroir exact de VALID_CATEGORIES (stackai/lib/constants.ts)
VALID_CATEGORIES: tuple[str, ...] = (
    "copywriting",
    "image",
    "automation",
    "analytics",
    "customer_service",
    "seo",
    "prospecting",
    "coding",
    "research",
    "video",
    "website",
)

ValidCategoryLiteral = Literal[
    "copywriting",
    "image",
    "automation",
    "analytics",
    "customer_service",
    "seo",
    "prospecting",
    "coding",
    "research",
    "video",
    "website",
]

RRF_K = 60

# Bonus matcher : intégration alignée sur une tâche parente (graphe depends_on)
DEPENDENCY_INTEGRATION_BONUS = 15
DEPENDENCY_INTEGRATION_BONUS_CAP = 15
