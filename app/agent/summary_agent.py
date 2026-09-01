import json
import logging

import ollama

from app.agent.review_policy import ReviewPolicy
from app.agent.utils import extract_json

logger = logging.getLogger(__name__)


class SummaryAgent:
    """Synthesizes findings from all review agents into an overall assessment.

    Not a BaseReviewAgent subclass — it takes merged findings rather than raw diff.
    """

    def __init__(self, policy: ReviewPolicy):
        config = policy.get_agent_config("summary")
        self.enabled = config["enabled"]
        self.model = config["model"]

    async def summarize(self, findings: list[dict], diff: str) -> dict:
        """Produce a summary from merged findings + diff context."""
        if not self.enabled:
            return self._fallback_summary(findings)

        findings_text = json.dumps(findings, indent=2) if findings else "No findings."

        prompt = f"""You are a senior engineering lead reviewing the aggregated findings from multiple specialized code review agents.

AGGREGATED FINDINGS:
{findings_text}

CODE CHANGES OVERVIEW (first 1000 chars):
{diff[:1000]}

Produce a concise overall assessment. Return ONLY valid JSON with this structure:

{{
    "summary": "2-3 sentence overall assessment of the PR quality and risk",
    "risk_level": "LOW|MEDIUM|HIGH|CRITICAL",
    "key_concerns": ["concern 1", "concern 2"],
    "recommendations": ["recommendation 1", "recommendation 2"]
}}

Guidelines:
- risk_level should reflect the highest-severity finding
- key_concerns should highlight the most important issues (max 5)
- recommendations should be actionable next steps (max 5)
- If there are no findings, return LOW risk with an appropriate summary"""

        try:
            client = ollama.AsyncClient()
            response = await client.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
            )
            result = extract_json(response["message"]["content"])
            if result.get("summary"):
                return result
        except Exception as e:
            logger.warning("[summary] LLM call failed: %s", e)

        return self._fallback_summary(findings)

    def _fallback_summary(self, findings: list[dict]) -> dict:
        """Generate a basic summary from severity counts when LLM is unavailable."""
        severity_counts = {}
        for f in findings:
            sev = f.get("severity", "LOW").upper()
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        total = len(findings)
        critical = severity_counts.get("CRITICAL", 0)
        high = severity_counts.get("HIGH", 0)

        if critical > 0:
            risk = "CRITICAL"
        elif high > 0:
            risk = "HIGH"
        elif total > 0:
            risk = "MEDIUM"
        else:
            risk = "LOW"

        parts = [f"{count} {sev}" for sev, count in sorted(severity_counts.items())]
        counts_str = ", ".join(parts) if parts else "no issues"

        return {
            "summary": f"Review found {total} issues ({counts_str}).",
            "risk_level": risk,
            "key_concerns": [],
            "recommendations": [],
        }
