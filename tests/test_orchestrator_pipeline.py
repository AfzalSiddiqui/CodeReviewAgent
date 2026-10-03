"""Tests for the pure pipeline steps of the Orchestrator.

The Orchestrator is created without __init__ so no LLM, vector store
or GitHub calls are made.
"""
import pytest

from app.agent.orchestrator import Orchestrator


@pytest.fixture
def orch():
    return Orchestrator.__new__(Orchestrator)


def finding(file="app.py", line=10, category="security", severity="LOW", **extra):
    return {"file": file, "line": line, "category": category, "severity": severity,
            "issue": "issue", "recommendation": "fix it", **extra}


def test_deduplicate_keeps_highest_severity(orch):
    result = orch._deduplicate([finding(severity="LOW"), finding(severity="CRITICAL"), finding(severity="MEDIUM")])
    assert len(result) == 1
    assert result[0]["severity"] == "CRITICAL"


def test_deduplicate_keeps_distinct_findings(orch):
    result = orch._deduplicate([finding(line=1), finding(line=2), finding(line=1, category="logic")])
    assert len(result) == 3


def test_validate_drops_hallucinated_files_and_lines(orch):
    valid = {"app.py": {10, 11}}
    findings = [
        finding(),                       # valid
        finding(line=99),                # line not in diff
        finding(file="ghost.py"),        # file not in PR
        finding(file=None),              # missing file
        finding(line=None),              # missing line
    ]
    kept = orch._validate_findings(findings, valid)
    assert kept == [findings[0]]


def test_build_diff_tags_lines_and_maps_valid_lines(orch):
    files = [
        {"filename": "a.py", "patch": "@@ -1,1 +1,2 @@\n ctx\n+new"},
        {"filename": "binary.png"},  # no patch: skipped
    ]
    diff, valid = orch._build_diff(files)
    assert "FILE: a.py" in diff
    assert "2 | [ADDED] new" in diff
    assert "1 | [CONTEXT] ctx" in diff
    assert valid == {"a.py": {1, 2}}


def test_build_comments_formats_agent_label_and_suggestion(orch):
    comments = orch._build_comments([finding(agent="security", severity="HIGH", suggestion="x = safe()")])
    assert comments[0]["path"] == "app.py"
    assert comments[0]["line"] == 10
    body = comments[0]["body"]
    assert body.startswith("**[security]**")
    assert "```suggestion\nx = safe()\n```" in body
