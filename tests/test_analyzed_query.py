import pytest
from pydantic import ValidationError

from app.domain.analyzed_query import (
    AnalyzedQuery,
    AtomicSubtask,
    FunctionalDomain,
    QueryAnalyzerPass1Output,
    ValidCategory,
)
from app.domain.query_fallback import build_bulletproof_fallback, detect_categories_from_text
from app.infra.llm.parse import validate_llm_output


def test_fallback_never_empty_categories():
    q = build_bulletproof_fallback("Lancer ma boutique Shopify", "ecommerce", 50)
    assert len(q.required_categories) >= 1
    assert ValidCategory.AUTOMATION in q.required_categories


def test_fallback_shopify_has_concrete_actions():
    q = build_bulletproof_fallback("Lancer ma boutique Shopify", "ecommerce", 50)
    joined = " ".join(q.subtasks).lower()
    assert "contribuer à l'objectif" not in joined
    assert "shopify" in joined or "fiches produit" in joined
    assert len(q.subtasks) >= 3


def test_detect_shopify_automation():
    cats = detect_categories_from_text("Automatiser ma boutique Shopify")
    assert ValidCategory.AUTOMATION in cats


def test_duplicate_id_rejected():
    with pytest.raises(ValidationError):
        AnalyzedQuery(
            original="x",
            budget_max=0,
            domains=[
                FunctionalDomain(
                    name="d",
                    priority=1,
                    subtasks=[
                        AtomicSubtask(
                            id="t1",
                            action="a",
                            required_category=ValidCategory.SEO,
                            depends_on=[],
                        ),
                        AtomicSubtask(
                            id="t1",
                            action="b",
                            required_category=ValidCategory.SEO,
                            depends_on=[],
                        ),
                    ],
                )
            ],
        )


def test_self_dependency_rejected():
    with pytest.raises(ValidationError):
        AnalyzedQuery(
            original="x",
            budget_max=0,
            domains=[
                FunctionalDomain(
                    name="d",
                    priority=1,
                    subtasks=[
                        AtomicSubtask(
                            id="t1",
                            action="a",
                            required_category=ValidCategory.AUTOMATION,
                            depends_on=["t1"],
                        ),
                    ],
                )
            ],
        )


def test_pass1_json_validates():
    raw = """
    {
      "subtasks": [
        {
          "id": "t1",
          "action": "Capturer des leads",
          "required_category": "prospecting",
          "depends_on": []
        },
        {
          "id": "t2",
          "action": "Envoyer des emails",
          "required_category": "automation",
          "depends_on": ["t1"]
        }
      ],
      "sector_context": "B2B",
      "implicit_constraints": []
    }
    """
    out = validate_llm_output(raw, QueryAnalyzerPass1Output)
    q = out.to_analyzed_query("Objectif test", 200)
    assert q.required_category_values == ["automation", "prospecting"]
    assert q.subtasks[1] == "Envoyer des emails"
