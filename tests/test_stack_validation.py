from app.core.models import ScoredAgent
from app.pipeline.fallbacks.selection import fallback_selection_from_candidates
from app.pipeline.stack_validation import refill_after_redundancy, trim_to_budget


def _agent(id_: str, name: str, price: float, score: int = 80) -> ScoredAgent:
    return ScoredAgent(
        id=id_,
        name=name,
        category="automation",
        description="test",
        price_from=price,
        score=float(score),
        roi_score=float(score),
        relevance_score=score,
        relevance_reason="test",
        use_cases=["uc"],
        compatible_with=[],
        website_domain="x.com",
        setup_difficulty="easy",
        time_to_value="fast",
        similarity=0.9,
    )


def test_trim_to_budget_can_go_below_min_tools_for_tight_budget():
    tools = [
        _agent("1", "A", 29),
        _agent("2", "B", 19),
        _agent("3", "C", 10),
        _agent("4", "D", 5),
    ]
    trimmed, warnings = trim_to_budget(tools, budget_max=50, min_tools=4)
    assert sum(t.price_from for t in trimmed) <= 50
    assert len(trimmed) >= 3
    assert any("strict" in w for w in warnings)


def test_trim_to_budget_keeps_minimum():
    tools = [_agent("1", "A", 30), _agent("2", "B", 30), _agent("3", "C", 10)]
    trimmed, warnings = trim_to_budget(tools, budget_max=50, min_tools=2)
    assert len(trimmed) == 2
    assert sum(t.price_from for t in trimmed) <= 50
    assert warnings


def test_refill_after_redundancy_adds_distinct_group():
    chat1 = _agent("1", "Tidio AI", 29, 90)
    chat2 = _agent("2", "Webbotify", 19, 85)
    seo = _agent("3", "Ahrefs", 15, 80)
    candidates = [chat1, chat2, seo, _agent("4", "Klaviyo", 0, 75)]
    after = refill_after_redundancy(
        [chat1],
        candidates,
        min_tools=3,
        max_tools=6,
        budget_max=50,
    )[0]
    assert len(after) >= 3
    names = {a.name for a in after}
    assert "Tidio AI" in names
    assert len(names) == len(after)


def test_fallback_prefers_one_per_redundancy_group():
    candidates = [
        _agent("1", "Tidio AI", 29, 95),
        _agent("2", "Webbotify", 19, 90),
        _agent("3", "Ahrefs", 10, 85),
        _agent("4", "Klaviyo", 0, 80),
    ]
    ids, _, _ = fallback_selection_from_candidates(
        candidates,
        ["t1", "t2", "t3", "t4"],
        min_tools=3,
        max_tools=4,
        budget_max=50,
    )
    assert len(ids) >= 3
    names = [c.name for c in candidates if c.id in ids]
    assert sum(1 for n in names if n in ("Tidio AI", "Webbotify")) <= 1
