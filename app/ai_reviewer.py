import json
import re
import ollama


class AIReviewer:

    def __init__(self, model="qwen2.5-coder:7b"):
        self.model = model

    def _extract_json(self, text: str) -> dict:
        """Extract and parse JSON from model output, handling common issues."""
        content = text.strip()

        # Remove Markdown code fences
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]

        if content.endswith("```"):
            content = content[:-3]

        content = content.strip()

        # First try: parse directly
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        # Second try: extract the first { ... } block
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        # Give up — return empty review
        print(f"WARNING: Could not parse AI response as JSON:\n{content[:500]}")
        return {
            "summary": "Review could not be parsed.",
            "risk_level": "LOW",
            "findings": [],
            "recommendations": [],
        }

    def review(self, structured_diff: str, checklist: dict):

        prompt = f"""
You are a senior software engineer performing an automated GitHub Pull Request code review.

Review ONLY the code changes provided below.

REVIEW CHECKLIST:
{json.dumps(checklist, indent=2)}

CODE CHANGES (with exact line numbers):
{structured_diff}

Check for meaningful issues related to:

- Code quality
- Business logic
- Security
- Performance
- Architecture
- Testing
- Logging
- Modern engineering practices
- Maintainability
- Scalability

Do not report issues that are purely stylistic unless they affect maintainability,
security, reliability, performance, or correctness.

IMPORTANT RULES FOR FINDINGS:

1. Every finding MUST refer to a specific line from the CODE CHANGES above.
2. "file" MUST be the exact file path shown in the CODE CHANGES.
3. "line" MUST be one of the exact line numbers shown in the CODE CHANGES (the number before the | character).
4. NEVER return "line": null.
5. NEVER invent a line number — only use numbers that appear in the CODE CHANGES listing.
6. Focus on lines marked [ADDED] as those are newly introduced changes.
7. If an issue cannot be mapped to a specific line, do not include it as a finding.
8. Keep findings focused on meaningful issues.
9. In "suggestion", provide the exact replacement code for that line.

Return ONLY valid JSON. Do not include any text before or after the JSON object.

Use exactly this structure:

{{
    "summary": "Short overall review",
    "risk_level": "LOW",
    "findings": [
        {{
            "category": "security",
            "severity": "HIGH",
            "file": "exact/path/from/above.py",
            "line": 42,
            "issue": "Clear description of the problem",
            "recommendation": "Explanation of how to fix it",
            "suggestion": "the corrected line of code"
        }}
    ],
    "recommendations": [
        "General recommendation 1"
    ]
}}

The allowed risk levels are: LOW, MEDIUM, HIGH, CRITICAL
The allowed severity levels are: LOW, MEDIUM, HIGH, CRITICAL
"""

        max_attempts = 2

        for attempt in range(max_attempts):
            response = ollama.chat(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            result = self._extract_json(response["message"]["content"])

            if result.get("findings") is not None:
                return result

            print(f"AI review attempt {attempt + 1} returned bad JSON, retrying...")

        return result
