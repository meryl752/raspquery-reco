from app.core.models import UserContext, VectorAgent
from app.domain.analyzed_query import AnalyzedQuery, AtomicSubtask, FunctionalDomain, ValidCategory
from app.pipeline.matcher import match_agents


def _ctx() -> UserContext:
    return UserContext(
        objective="Automatiser prospection",
        sector="b2b",
        budget="low",
        tech_level="beginner",
    )


def _query_with_airtable_chain() -> AnalyzedQuery:
    return AnalyzedQuery(
        original="CRM puis emails",
        budget_max=50,
        domains=[
            FunctionalDomain(
                name="sales",
                priority=1,
                subtasks=[
                    AtomicSubtask(
                        id="t1",
                        action="Centraliser les leads dans Airtable",
                        required_category=ValidCategory.PROSPECTING,
                        depends_on=[],
                    ),
                    AtomicSubtask(
                        id="t2",
                        action="Relancer par email",
                        required_category=ValidCategory.AUTOMATION,
                        depends_on=["t1"],
                    ),
                ],
            )
        ],
    )


def test_integration_bonus_for_parent_tool():
    agents = [
        VectorAgent(
            id="1",
            name="ToolA",
            category="automation",
            description="",
            price_from=0,
            score=80,
            roi_score=70,
            similarity=0.5,
            integrations=["Airtable", "Slack"],
        ),
        VectorAgent(
            id="2",
            name="ToolB",
            category="automation",
            description="",
            price_from=0,
            score=80,
            roi_score=70,
            similarity=0.5,
            integrations=[],
        ),
    ]
    result = match_agents(agents, _query_with_airtable_chain(), _ctx())
    assert len(result) == 2
    assert result[0].name == "ToolA"
    assert "chaîne" in result[0].relevance_reason or result[0].relevance_score >= result[1].relevance_score
