import json

from app.agent.base_agent import BaseReviewAgent


class PerformanceAgent(BaseReviewAgent):

    @property
    def name(self) -> str:
        return "performance"

    def build_prompt(self, diff: str, checklist: dict, rag_context: str) -> str:
        rag_section = ""
        if rag_context:
            rag_section = f"""
REPOSITORY-SPECIFIC PERFORMANCE GUIDELINES:
{rag_context}

Apply these guidelines in addition to standard checks.
"""

        return f"""You are a senior performance engineer performing a focused performance review of a GitHub Pull Request.

Your ONLY job is to find performance issues. Ignore style, security, and logic correctness issues.

PERFORMANCE CHECKLIST:
{json.dumps(checklist, indent=2)}
{rag_section}
Focus areas:
- O(n²) or worse algorithms where O(n) or O(n log n) is possible
- Unnecessary memory allocations (creating objects in loops, large copies)
- N+1 query patterns (database queries inside loops)
- Blocking I/O in async contexts
- Missing caching for expensive repeated computations
- Unnecessary network calls or redundant API requests
- Large payload sizes or missing pagination
- Inefficient string concatenation in loops
- Resource leaks (unclosed connections, file handles)

CODE CHANGES (with exact line numbers):
{diff}

{self._build_rules()}

Use exactly this structure:
{self._build_json_schema()}

The allowed severity levels are: LOW, MEDIUM, HIGH, CRITICAL"""
