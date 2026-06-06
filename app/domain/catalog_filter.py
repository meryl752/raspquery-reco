"""Filtre ICP — même logique que stackai/lib/catalog/icpFilter.ts."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TypeVar

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

_cache: dict | None = None


def _default_filter_path() -> Path:
    root = Path(__file__).resolve().parents[2]
    bundled = root / "data" / "catalog-filter.json"
    if bundled.is_file():
        return bundled
    return root / ".." / "stackai" / "data" / "catalog-filter.json"


def _resolve_path(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    if settings.catalog_filter_path:
        return Path(settings.catalog_filter_path)
    return _default_filter_path().resolve()


def _load_filter(path: Path) -> tuple[set[str], set[str], list[str]]:
    if not path.is_file():
        return set(), set(), []

    raw = json.loads(path.read_text(encoding="utf-8"))
    excluded_ids = {str(x).strip().lower() for x in raw.get("excluded_agent_ids", [])}
    excluded_names = {str(x).strip().lower() for x in raw.get("excluded_names_exact", [])}
    name_contains = [
        str(x).strip().lower()
        for x in raw.get("excluded_name_contains", [])
        if str(x).strip()
    ]
    return excluded_ids, excluded_names, name_contains


def get_catalog_filter(settings: Settings | None = None) -> tuple[set[str], set[str], list[str]]:
    global _cache
    path = _resolve_path(settings)
    mtime = path.stat().st_mtime if path.is_file() else 0
    if _cache and _cache.get("mtime") == mtime and _cache.get("path") == str(path):
        return _cache["data"]

    try:
        data = _load_filter(path)
        _cache = {"mtime": mtime, "path": str(path), "data": data}
        return data
    except Exception as exc:
        logger.warning("catalog-filter load failed: %s", exc)
        return set(), set(), []


def _is_excluded(agent: object, excluded_ids: set[str], excluded_names: set[str], frags: list[str]) -> bool:
    aid = str(getattr(agent, "id", "")).strip().lower()
    name = str(getattr(agent, "name", "")).strip().lower()
    if aid in excluded_ids or name in excluded_names:
        return True
    return any(frag in name for frag in frags if frag)


def filter_catalog_agents(agents: list[T]) -> list[T]:
    if not agents:
        return agents
    excluded_ids, excluded_names, name_contains = get_catalog_filter()
    if not excluded_ids and not excluded_names and not name_contains:
        return agents

    kept = [a for a in agents if not _is_excluded(a, excluded_ids, excluded_names, name_contains)]
    removed = len(agents) - len(kept)
    if removed:
        logger.info(
            "catalog-filter: %d agent(s) retiré(s) (%d → %d)",
            removed,
            len(agents),
            len(kept),
        )
    return kept
