"""Rôles agents — aligné stackai/lib/agents/roleCopy.ts."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.models import AppLocale

MAX_ROLE_WORDS = 18
MAX_ROLE_CHARS = 140
MAX_CONTEXT_DESC_CHARS = 220


@dataclass
class ToolLike:
    name: str
    description: str = ""
    use_cases: list[str] | None = None
    best_for: list[str] | None = None
    assigned_subtask: str = ""


def truncate_catalog_snippet(text: str, max_len: int = MAX_CONTEXT_DESC_CHARS) -> str:
    t = " ".join((text or "").split())
    if len(t) <= max_len:
        return t
    return f"{t[: max_len - 1].strip()}…"


def truncate_role_text(text: str) -> str:
    t = " ".join((text or "").split())
    if not t:
        return t
    words = t.split()
    if len(words) > MAX_ROLE_WORDS:
        return f"{' '.join(words[:MAX_ROLE_WORDS])}…"
    if len(t) > MAX_ROLE_CHARS:
        return f"{t[: MAX_ROLE_CHARS - 1].strip()}…"
    return t


def looks_like_catalog_description(role: str, catalog_description: str) -> bool:
    r = role.strip()
    if len(r) > 100:
        return True
    if not (catalog_description or "").strip():
        return False
    desc_start = catalog_description.strip().lower()[:48]
    role_start = r.lower()[:48]
    if len(desc_start) >= 24 and (
        desc_start[:24] in role_start or role_start[:24] in desc_start
    ):
        return True
    return False


def build_deterministic_role(
    tool: ToolLike,
    user_objective: str,
    locale: AppLocale = "en",
) -> str:
    sub = (tool.assigned_subtask or "").strip()
    use_case = (tool.use_cases or [None])[0]
    use_case = (use_case or "").strip() if use_case else ""
    is_fr = locale == "fr"

    if sub:
        return truncate_role_text(
            f"Pour votre objectif, {tool.name} couvre : {sub}"
            if is_fr
            else f"For your goal, {tool.name} handles: {sub}"
        )

    if use_case:
        obj = user_objective.strip()[:60]
        suffix = "…" if len(user_objective.strip()) > 60 else ""
        if is_fr:
            return truncate_role_text(
                f"{tool.name} — {use_case} (lié à : {obj}{suffix})"
                if obj
                else f"{tool.name} — {use_case}"
            )
        return truncate_role_text(
            f"{tool.name} — {use_case} (for: {obj}{suffix})"
            if obj
            else f"{tool.name} — {use_case}"
        )

    return truncate_role_text(
        f"{tool.name} dans votre stack" if is_fr else f"{tool.name} in your stack"
    )


def normalize_stack_agent_role(
    raw_role: str | None,
    tool: ToolLike,
    user_objective: str,
    locale: AppLocale = "en",
) -> str:
    trimmed = (raw_role or "").strip()
    if not trimmed or looks_like_catalog_description(trimmed, tool.description):
        return build_deterministic_role(tool, user_objective, locale)
    return truncate_role_text(trimmed)


def impact_level_from_roi(roi_score: float, locale: AppLocale = "fr") -> str:
    if roi_score >= 80:
        return "élevé" if locale == "fr" else "high"
    if roi_score >= 50:
        return "moyen" if locale == "fr" else "medium"
    return "modéré" if locale == "fr" else "moderate"
