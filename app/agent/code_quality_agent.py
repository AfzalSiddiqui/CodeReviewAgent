import json

from app.agent.base_agent import BaseReviewAgent


class CodeQualityAgent(BaseReviewAgent):

    @property
    def name(self) -> str:
        return "code_quality"

    def build_prompt(self, diff: str, checklist: dict, rag_context: str) -> str:
        rag_section = ""
        if rag_context:
            rag_section = f"""
REPOSITORY-SPECIFIC QUALITY STANDARDS:
{rag_context}

Apply these standards in addition to standard checks.
"""

        return f"""You are a senior software engineer performing a focused code quality review of a GitHub Pull Request.

Your ONLY job is to find code quality, architecture, and maintainability issues. Ignore security and performance issues.

QUALITY CHECKLIST:
{json.dumps(checklist, indent=2)}
{rag_section}
Focus areas:
- Readability: unclear variable/function names, overly complex expressions
- Single Responsibility Principle violations
- Code duplication that should be extracted
- Excessive complexity (deeply nested conditionals, long functions)
- Separation of concerns violations
- Deprecated API usage and outdated patterns
- Missing or misleading logging
- Dependency management issues (tight coupling, circular dependencies)
- Scalability concerns in architecture
- Developer experience (confusing APIs, missing type hints on public interfaces)

Only report issues that meaningfully affect maintainability, reliability, or correctness.
Do NOT report purely stylistic preferences.

CODE CHANGES (with exact line numbers):
{diff}

{self._build_rules()}

Use exactly this structure:
{self._build_json_schema()}

The allowed severity levels are: LOW, MEDIUM, HIGH, CRITICAL"""
