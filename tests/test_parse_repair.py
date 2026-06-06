import json

import pytest

from app.infra.llm.parse import parse_llm_json, repair_json_text


def test_repair_invalid_unicode_escape():
    raw = '{"selected_ids": ["a"], "note": "test \\u12"}'
    repaired = repair_json_text(raw)
    json.loads(repaired)


def test_parse_extracts_object():
    raw = 'Here is JSON:\n```json\n{"selected_ids": ["x"], "warnings": []}\n```'
    data = parse_llm_json(raw)
    assert data["selected_ids"] == ["x"]
