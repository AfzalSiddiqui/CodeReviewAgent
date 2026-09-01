import json

from app.agent.base_agent import BaseReviewAgent


class LogicBugAgent(BaseReviewAgent):

    @property
    def name(self) -> str:
        return "logic_bug"

    def build_prompt(self, diff: str, checklist: dict, rag_context: str) -> str:
        rag_section = ""
        if rag_context:
            rag_section = f"""
REPOSITORY-SPECIFIC LOGIC PATTERNS:
{rag_context}

Apply these patterns in addition to standard checks.
"""

        return f"""You are a senior software engineer performing a focused logic and correctness review of a GitHub Pull Request.

Your ONLY job is to find logic bugs and correctness issues. Ignore style, security, and performance issues.

LOGIC CHECKLIST:
{json.dumps(checklist, indent=2)}
{rag_section}
Focus areas:
- Off-by-one errors in loops, slicing, and indexing
- Null/None/undefined reference errors
- Unhandled edge cases (empty inputs, boundary values, negative numbers)
- Wrong boolean operators (and vs or, == vs !=)
- Incorrect conditional logic (inverted conditions, missing branches)
- Race conditions and concurrency bugs
- Wrong variable used (copy-paste errors)
- Missing return statements or wrong return values
- Integer overflow/underflow
- Incorrect error handling (swallowed exceptions, wrong exception types)

CODE CHANGES (with exact line numbers):
{diff}

{self._build_rules()}

Use exactly this structure:
{self._build_json_schema()}

The allowed severity levels are: LOW, MEDIUM, HIGH, CRITICAL"""
