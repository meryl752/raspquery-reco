"""Normalise les JSON LLM vers les schémas Pydantic (alias tasks/taches, etc.)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.domain.analyzed_query import (
    QueryAnalyzerPass1Output,
    QueryAnalyzerPass2Output,
    coerce_category,
)


def _first_task_list(data: dict[str, Any]) -> list[Any] | None:
    for key in (
        "subtasks",
        "tasks",
        "taches",
        "sous_taches",
        "sous-taches",
        "steps",
        "etapes",
    ):
        val = data.get(key)
        if isinstance(val, list) and val:
            return val
    for val in data.values():
        if isinstance(val, dict):
            nested = _first_task_list(val)
            if nested:
                return nested
    return None


def normalize_pass1_payload(data: Any) -> dict[str, Any]:
    if isinstance(data, list):
        data = {"subtasks": data}
    if not isinstance(data, dict):
        raise ValueError("pass1: JSON racine doit être un objet")

    d = dict(data)
    rows = d.get("subtasks")
    if not isinstance(rows, list) or not rows:
        found = _first_task_list(d)
        if found:
            rows = found
        else:
            rows = []

    normalized: list[dict[str, Any]] = []
    for i, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        r = dict(row)
        r["id"] = str(r.get("id") or f"t{i}").strip() or f"t{i}"

        action = (
            r.get("action")
            or r.get("description")
            or r.get("name")
            or r.get("tache")
            or r.get("task")
            or r.get("title")
        )
        r["action"] = str(action).strip() if action else f"Sous-tâche {i}"

        cat_raw = (
            r.get("required_category")
            or r.get("category")
            or r.get("categorie")
            or r.get("requiredCategory")
            or "automation"
        )
        coerced = coerce_category(str(cat_raw))
        r["required_category"] = coerced.value if coerced else "automation"

        deps = r.get("depends_on") or r.get("dependencies") or r.get("dependsOn") or []
        if isinstance(deps, list):
            r["depends_on"] = [str(x).strip() for x in deps if str(x).strip()]
        else:
            r["depends_on"] = []

        if "can_be_automated" not in r:
            r["can_be_automated"] = True

        normalized.append(r)

    if not normalized:
        raise ValueError("pass1: aucune sous-tâche exploitable dans le JSON LLM")

    sector = (
        d.get("sector_context")
        or d.get("contexte_secteur")
        or d.get("sectorContext")
        or ""
    )

    constraints = d.get("implicit_constraints") or d.get("constraints") or d.get("contraintes") or []
    if not isinstance(constraints, list):
        constraints = []

    return {
        "subtasks": normalized,
        "sector_context": str(sector) if sector else "",
        "implicit_constraints": [str(c) for c in constraints],
    }


def normalize_stack_selection_payload(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("selection: JSON objet requis")
    d = dict(data)
    ids = d.get("selected_ids") or d.get("selectedIds") or d.get("ids") or []
    if not ids and isinstance(d.get("tools"), list):
        for item in d["tools"]:
            if isinstance(item, str):
                ids.append(item)
            elif isinstance(item, dict) and item.get("id"):
                ids.append(str(item["id"]))
    cov = d.get("subtask_coverage") or d.get("subtaskCoverage") or {}
    warnings = d.get("warnings") or []
    return {
        "selected_ids": [str(x) for x in ids] if isinstance(ids, list) else [],
        "subtask_coverage": cov if isinstance(cov, dict) else {},
        "warnings": warnings if isinstance(warnings, list) else [],
    }


def _extract_domain_task_ids(
    row: dict[str, Any],
    known_task_ids: list[str] | None,
) -> list[str]:
    ids: list[str] = []
    known_set = set(known_task_ids or [])

    def _add(raw: Any) -> None:
        if isinstance(raw, str) and raw.strip():
            tid = raw.strip()
            if not known_set or tid in known_set:
                ids.append(tid)
        elif isinstance(raw, int) and known_task_ids and 0 <= raw < len(known_task_ids):
            ids.append(known_task_ids[raw])
        elif isinstance(raw, int):
            ids.append(f"t{raw + 1}")

    for key in ("task_ids", "taskIds", "subtask_ids", "ids"):
        val = row.get(key)
        if isinstance(val, list):
            for item in val:
                _add(item)

    for key in ("task_indices", "indices", "taskIndexes"):
        val = row.get(key)
        if isinstance(val, list):
            for item in val:
                _add(item)

    for key in ("subtasks", "tasks", "taches"):
        val = row.get(key)
        if not isinstance(val, list):
            continue
        for item in val:
            if isinstance(item, dict):
                _add(item.get("id"))
            else:
                _add(item)

    seen: set[str] = set()
    out: list[str] = []
    for tid in ids:
        if tid not in seen:
            seen.add(tid)
            out.append(tid)
    return out


def normalize_pass2_payload(
    data: Any,
    known_task_ids: list[str] | None = None,
) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("pass2: JSON racine doit être un objet")

    d = dict(data)
    domains = d.get("domains") or d.get("domaines") or d.get("functional_domains")
    if not isinstance(domains, list):
        raise ValueError("pass2: champ domains manquant")

    out_domains: list[dict[str, Any]] = []
    for i, dom in enumerate(domains, start=1):
        if not isinstance(dom, dict):
            continue
        row = dict(dom)
        name = row.get("name") or row.get("nom") or f"Domaine {i}"
        priority = row.get("priority") or row.get("priorite") or i
        task_ids = _extract_domain_task_ids(row, known_task_ids)
        if not task_ids:
            continue
        out_domains.append(
            {
                "name": str(name),
                "priority": int(priority),
                "task_ids": task_ids,
            }
        )

    if not out_domains:
        raise ValueError("pass2: aucun domaine avec task_ids valides")

    return {"domains": out_domains}


def validate_llm_model(
    data: dict[str, Any],
    model: type[BaseModel],
    *,
    known_task_ids: list[str] | None = None,
) -> BaseModel:
    from app.pipeline.stack_builder import StackSelectionOutput

    if model is QueryAnalyzerPass1Output:
        data = normalize_pass1_payload(data)
    elif model is QueryAnalyzerPass2Output:
        data = normalize_pass2_payload(data, known_task_ids=known_task_ids)
    elif model is StackSelectionOutput:
        data = normalize_stack_selection_payload(data)
    return model.model_validate(data)
