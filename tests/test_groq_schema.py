from app.domain.analyzed_query import QueryAnalyzerPass1Output
from app.infra.llm.schema import (
    build_groq_response_format,
    model_supports_json_schema,
)


def test_qwen_uses_json_object_not_schema():
    assert not model_supports_json_schema("qwen/qwen3-32b")
    fmt = build_groq_response_format(
        QueryAnalyzerPass1Output,
        "pass1",
        use_json_schema=model_supports_json_schema("qwen/qwen3-32b"),
    )
    assert fmt == {"type": "json_object"}


def test_gpt_oss_uses_json_schema():
    assert model_supports_json_schema("openai/gpt-oss-20b")
    fmt = build_groq_response_format(
        QueryAnalyzerPass1Output,
        "pass1",
        use_json_schema=True,
    )
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["name"] == "pass1"
    schema = fmt["json_schema"]["schema"]
    assert "properties" in schema
    assert "$defs" not in schema
