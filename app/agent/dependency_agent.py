import json

from app.agent.base_agent import BaseReviewAgent


class DependencyAgent(BaseReviewAgent):

    @property
    def name(self) -> str:
        return "dependency"

    def build_prompt(self, diff: str, checklist: dict, rag_context: str) -> str:
        rag_section = ""
        if rag_context:
            rag_section = f"""
REPOSITORY-SPECIFIC DEPENDENCY POLICIES:
{rag_context}

Apply these policies in addition to standard checks.
"""

        return f"""You are a senior software engineer performing a focused dependency review of a GitHub Pull Request.

Your ONLY job is to find dependency and import issues. Ignore style, logic, and performance issues.

DEPENDENCY CHECKLIST:
{json.dumps(checklist, indent=2)}
{rag_section}
Focus areas:
- Incorrect or missing imports
- Importing from internal/private modules that may change
- Version conflicts between dependencies
- Unused imports or dependencies
- Known vulnerable package versions
- Circular import patterns
- Missing dependency declarations (requirements.txt, package.json, etc.)
- Pinning to exact versions vs using ranges appropriately

CODE CHANGES (with exact line numbers):
{diff}

{self._build_rules()}

Use exactly this structure:
{self._build_json_schema()}

The allowed severity levels are: LOW, MEDIUM, HIGH, CRITICAL"""
