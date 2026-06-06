from app.domain.analyzed_query import QueryAnalyzerPass1Output, QueryAnalyzerPass2Output
from app.infra.llm.coerce import normalize_pass1_payload, validate_llm_model


def test_tasks_alias_normalized():
    raw = {
        "tasks": [
            {
                "id": "t1",
                "description": "Optimiser le SEO produit",
                "category": "seo",
                "depends_on": [],
            }
        ],
        "sector_context": "ecommerce Shopify",
    }
    out = validate_llm_model(raw, QueryAnalyzerPass1Output)
    assert len(out.subtasks) == 1
    assert out.subtasks[0].required_category.value == "seo"


def test_pass2_domaines_alias():
    raw = {
        "domaines": [
            {"nom": "Marketing", "priorite": 1, "task_indices": [0, 1]},
        ]
    }
    out = validate_llm_model(
        raw, QueryAnalyzerPass2Output, known_task_ids=["t1", "t2", "t3"]
    )
    assert out.domains[0].name == "Marketing"
    assert out.domains[0].task_ids == ["t1", "t2"]


def test_pass2_nested_subtasks_in_domain():
    raw = {
        "domains": [
            {
                "name": "SEO",
                "priority": 1,
                "subtasks": [{"id": "t1"}, {"id": "t2"}],
            },
        ]
    }
    out = validate_llm_model(raw, QueryAnalyzerPass2Output, known_task_ids=["t1", "t2"])
    assert out.domains[0].task_ids == ["t1", "t2"]
