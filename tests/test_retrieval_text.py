from app.core.models import UserContext
from app.domain.query_fallback import build_bulletproof_fallback
from app.pipeline.retrieval_text import build_retrieval_embedding_text


def test_build_retrieval_embedding_text_includes_context():
    ctx = UserContext(
        objective="Automatiser le support Shopify",
        sector="ecommerce",
        budget="medium",
        tech_level="beginner",
        current_tools=["Shopify"],
    )
    query = build_bulletproof_fallback("Support client Shopify", "ecommerce", 50)
    query.implicit_constraints = ["Budget serré"]
    query.sector_context = "Boutique DTC"
    text = build_retrieval_embedding_text(ctx, query)
    assert "Automatiser le support Shopify" in text
    assert "Boutique DTC" in text
    assert "Budget serré" in text
    assert "customer_service" in text or "automation" in text
