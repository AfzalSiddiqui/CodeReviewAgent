import json

from app.agent.base_agent import BaseReviewAgent


class TestCoverageAgent(BaseReviewAgent):

    @property
    def name(self) -> str:
        return "test_coverage"

    def build_prompt(self, diff: str, checklist: dict, rag_context: str) -> str:
        rag_section = ""
        if rag_context:
            rag_section = f"""
REPOSITORY-SPECIFIC TESTING STANDARDS:
{rag_context}

Apply these standards in addition to standard checks.
"""

        return f"""You are a senior QA engineer performing a focused test coverage review of a GitHub Pull Request.

Your ONLY job is to identify missing or inadequate tests. Ignore style, security, and performance issues.

TESTING CHECKLIST:
{json.dumps(checklist, indent=2)}
{rag_section}
Focus areas:
- New functions/methods without corresponding unit tests
- Missing edge case tests (empty inputs, nulls, boundary values)
- Changed logic without updated regression tests
- Error paths not tested (exception handling, error responses)
- Missing integration tests for new API endpoints
- Test assertions that are too weak (only checking existence, not values)
- Mocked dependencies that should be tested with real implementations

CODE CHANGES (with exact line numbers):
{diff}

{self._build_rules()}

Use exactly this structure:
{self._build_json_schema()}

The allowed severity levels are: LOW, MEDIUM, HIGH, CRITICAL"""
