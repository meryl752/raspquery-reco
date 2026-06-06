from app.pipeline.role_copy import (
    ToolLike,
    build_deterministic_role,
    looks_like_catalog_description,
    normalize_stack_agent_role,
    truncate_role_text,
)


def test_truncate_role_text_max_words():
    long = " ".join(["mot"] * 25)
    out = truncate_role_text(long)
    assert out.endswith("…")
    assert len(out.split()) <= 19


def test_normalize_rejects_catalog_copy():
    desc = "Plateforme tout-en-un pour automatiser votre marketing digital avec IA"
    raw = desc
    role = normalize_stack_agent_role(
        raw,
        ToolLike(name="TestTool", description=desc, assigned_subtask="Envoyer des emails"),
        "Automatiser ma boutique Shopify",
        "fr",
    )
    assert "TestTool" in role
    assert role != desc


def test_build_deterministic_role_uses_subtask():
    role = build_deterministic_role(
        ToolLike(name="Klaviyo", assigned_subtask="Configurer les emails de bienvenue"),
        "Objectif ecommerce",
        "fr",
    )
    assert "Klaviyo" in role
    assert "emails de bienvenue" in role


def test_looks_like_catalog_description():
    assert looks_like_catalog_description("x" * 120, "short")
