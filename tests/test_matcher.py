from app.core.models import UserContext, VectorAgent
from app.domain.analyzed_query import AnalyzedQuery, AtomicSubtask, FunctionalDomain, ValidCategory
from app.pipeline.matcher import match_agents


def _ctx(**kwargs) -> UserContext:
    base = {
        "objective": "Automatiser la prospection B2B pour une agence marketing",
        "sector": "marketing",
        "budget": "low",
        "tech_level": "beginner",
    }
    base.update(kwargs)
    return UserContext(**base)


def _query() -> AnalyzedQuery:
    return AnalyzedQuery(
        original="Prospection automatisée",
        budget_max=50,
        sector_context="marketing",
        domains=[
            FunctionalDomain(
                name="core",
                priority=1,
                subtasks=[
                    AtomicSubtask(
                        id="t1",
                        action="prospection",
                        required_category=ValidCategory.PROSPECTING,
                        depends_on=[],
                    ),
                    AtomicSubtask(
                        id="t2",
                        action="automation workflows",
                        required_category=ValidCategory.AUTOMATION,
                        depends_on=[],
                    ),
                ],
            )
        ],
    )


def test_eliminates_paid_agents_on_zero_budget():
    agents = [
        VectorAgent(
            id="1",
            name="Free",
            category="automation",
            description="",
            price_from=0,
            score=80,
            roi_score=70,
            similarity=0.9,
        ),
        VectorAgent(
            id="2",
            name="Paid",
            category="automation",
            description="",
            price_from=99,
            score=90,
            roi_score=80,
            similarity=0.95,
        ),
    ]
    result = match_agents(agents, _query(), _ctx(budget="zero"))
    assert len(result) == 1
    assert result[0].name == "Free"


def test_returns_at_most_15_agents():
    agents = [
        VectorAgent(
            id=str(i),
            name=f"Agent{i}",
            category="automation",
            description="",
            price_from=0,
            score=70 + i,
            roi_score=60,
            similarity=0.5 + i * 0.01,
        )
        for i in range(20)
    ]
    result = match_agents(agents, _query(), _ctx())
    assert len(result) <= 15
    assert result[0].relevance_score >= result[-1].relevance_score
