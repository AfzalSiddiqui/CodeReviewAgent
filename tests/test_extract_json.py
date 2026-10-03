from app.agent.utils import extract_json


def test_parses_plain_json():
    assert extract_json('{"risk_level": "HIGH", "findings": []}')["risk_level"] == "HIGH"


def test_strips_json_code_fence():
    text = '```json\n{"summary": "ok", "findings": []}\n```'
    assert extract_json(text)["summary"] == "ok"


def test_strips_plain_code_fence():
    assert extract_json('```\n{"a": 1}\n```') == {"a": 1}


def test_extracts_json_surrounded_by_prose():
    text = 'Here is my review:\n{"summary": "found issues", "findings": [1]}\nThanks!'
    result = extract_json(text)
    assert result["summary"] == "found issues"
    assert result["findings"] == [1]


def test_unparseable_output_returns_safe_default():
    result = extract_json("the model rambled and returned no JSON")
    assert result["risk_level"] == "LOW"
    assert result["findings"] == []
    assert result["recommendations"] == []
