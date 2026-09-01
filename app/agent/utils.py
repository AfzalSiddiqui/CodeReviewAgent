import json
import re


def extract_json(text: str) -> dict:
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
    return {
        "summary": "Review could not be parsed.",
        "risk_level": "LOW",
        "findings": [],
        "recommendations": [],
    }
