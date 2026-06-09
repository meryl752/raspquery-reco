from app.core.models import VectorAgent
from app.pipeline.retrieval_pool import merge_category_agents


def _agent(agent_id: str) -> VectorAgent:
    return VectorAgent(
        id=agent_id,
        name=f"Agent {agent_id}",
        category="automation",
        description="",
        price_from=10,
        similarity=0.8,
    )


def test_merge_skips_when_pool_large_enough():
    pool = [_agent(f"v{i}") for i in range(15)]
    merged = merge_category_agents(pool, [_agent("c1")])
    assert len(merged) == 15


def test_merge_adds_category_agents_when_pool_small():
    pool = [_agent("v1"), _agent("v2")]
    merged = merge_category_agents(pool, [_agent("c1"), _agent("c2"), _agent("v1")])
    assert [a.id for a in merged] == ["v1", "v2", "c1", "c2"]
