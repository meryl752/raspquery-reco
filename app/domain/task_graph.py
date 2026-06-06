"""
Graphe de dépendances des sous-tâches — ordre topologique et contexte parent pour le matcher.
"""

from __future__ import annotations

from collections import defaultdict, deque

from app.domain.analyzed_query import AnalyzedQuery, AtomicSubtask
from app.domain.query_fallback import extract_tool_tokens_from_text


def iter_all_subtasks(query: AnalyzedQuery) -> list[AtomicSubtask]:
    out: list[AtomicSubtask] = []
    for domain in sorted(query.domains, key=lambda d: d.priority):
        out.extend(domain.subtasks)
    return out


def topological_subtasks(query: AnalyzedQuery) -> list[AtomicSubtask]:
    """Ordre où les parents précèdent les enfants (stable)."""
    tasks = iter_all_subtasks(query)
    by_id = {t.id: t for t in tasks}
    in_degree: dict[str, int] = {t.id: 0 for t in tasks}
    children: dict[str, list[str]] = defaultdict(list)

    for t in tasks:
        for dep in t.depends_on:
            if dep in by_id:
                in_degree[t.id] += 1
                children[dep].append(t.id)

    queue = deque([tid for tid, deg in in_degree.items() if deg == 0])
    order: list[str] = []
    while queue:
        tid = queue.popleft()
        order.append(tid)
        for child in children[tid]:
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    # Cycle ou ids orphelins : garder l'ordre d'origine
    if len(order) != len(tasks):
        return tasks
    return [by_id[tid] for tid in order]


def parent_context_tokens(query: AnalyzedQuery) -> set[str]:
    """
    Tokens outils / intégrations mentionnés dans les actions des tâches parentes.
    Utilisé par le matcher pour bonus de compatibilité (+15).
    """
    ordered = topological_subtasks(query)
    tokens: set[str] = set()
    accumulated: set[str] = set()

    for task in ordered:
        # Les parents sont ceux listés dans depends_on
        for parent_id in task.depends_on:
            parent = next((t for t in ordered if t.id == parent_id), None)
            if parent:
                accumulated |= extract_tool_tokens_from_text(parent.action)
        accumulated |= extract_tool_tokens_from_text(task.action)
        tokens |= accumulated

    return tokens
