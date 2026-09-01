import json

from app.agent.base_agent import BaseReviewAgent


class SecurityAgent(BaseReviewAgent):

    @property
    def name(self) -> str:
        return "security"

    def build_prompt(self, diff: str, checklist: dict, rag_context: str) -> str:
        rag_section = ""
        if rag_context:
            rag_section = f"""
REPOSITORY-SPECIFIC SECURITY POLICIES:
{rag_context}

Apply these policies in addition to standard checks.
"""

        return f"""You are a senior security engineer performing a focused security review of a GitHub Pull Request.

Your ONLY job is to find security vulnerabilities. Ignore style, performance, and logic issues.

SECURITY CHECKLIST:
{json.dumps(checklist, indent=2)}
{rag_section}
Focus areas:
- Hardcoded secrets, API keys, tokens, passwords
- SQL/NoSQL injection, command injection, XSS
- Authentication and authorization flaws
- Insecure data handling (PII exposure, missing encryption)
- Sensitive data in logs
- OWASP Top 10 vulnerabilities
- Insecure deserialization
- Path traversal

CODE CHANGES (with exact line numbers):
{diff}

{self._build_rules()}

Use exactly this structure:
{self._build_json_schema()}

The allowed severity levels are: LOW, MEDIUM, HIGH, CRITICAL"""
