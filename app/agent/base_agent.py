import logging
from abc import ABC, abstractmethod

import ollama

from app.agent.review_policy import ReviewPolicy
from app.agent.utils import extract_json
from app.rag.vector_store import VectorStore

logger = logging.getLogger(__name__)


class BaseReviewAgent(ABC):
    """Abstract base class for all specialized review agents."""

    def __init__(self, policy: ReviewPolicy, vector_store: VectorStore):
        self.policy = policy
        self.vector_store = vector_store

        config = policy.get_agent_config(self.name)
        self.model = config["model"]
        self.categories = config["categories"]

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique agent identifier matching the YAML key."""
        ...

    @abstractmethod
    def build_prompt(self, diff: str, checklist: dict, rag_context: str) -> str:
        """Build the focused review prompt for this agent."""
        ...

    async def review(self, structured_diff: str) -> dict:
        """Run the review: get checklist, RAG context, call LLM, extract JSON."""
        checklist = self.policy.get_checks_for_categories(self.categories)
        rag_context = self._get_rag_context(structured_diff)
        prompt = self.build_prompt(structured_diff, checklist, rag_context)

        max_attempts = 2
        result = {}

        for attempt in range(max_attempts):
            try:
                client = ollama.AsyncClient()
                response = await client.chat(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                )
                result = extract_json(response["message"]["content"])

                if result.get("findings") is not None:
                    # Tag each finding with the agent name
                    for finding in result["findings"]:
                        finding["agent"] = self.name
                    return result

            except Exception as e:
                logger.warning(
                    "[%s] attempt %d failed: %s", self.name, attempt + 1, e,
                )

        # Return whatever we got (may be empty)
        return result

    def _get_rag_context(self, diff: str) -> str:
        """Query vector store for relevant policies scoped to this agent's categories."""
        try:
            snippet = diff[:500]
            results = self.vector_store.search(
                query=snippet,
                n_results=3,
                category_filter=self.categories[0] if self.categories else None,
            )
            documents = results.get("documents", [[]])[0]
            if documents:
                return "\n\n".join(documents)
        except Exception as e:
            logger.debug("[%s] RAG lookup failed: %s", self.name, e)

        return ""

    def _build_json_schema(self) -> str:
        return """{
    "findings": [
        {
            "category": "<category>",
            "severity": "LOW|MEDIUM|HIGH|CRITICAL",
            "file": "exact/path/from/above.py",
            "line": 42,
            "issue": "Clear description of the problem",
            "recommendation": "Explanation of how to fix it",
            "suggestion": "the corrected line of code"
        }
    ]
}"""

    def _build_rules(self) -> str:
        return """IMPORTANT RULES FOR FINDINGS:

1. Every finding MUST refer to a specific line from the CODE CHANGES above.
2. "file" MUST be the exact file path shown in the CODE CHANGES.
3. "line" MUST be one of the exact line numbers shown (the number before the | character).
4. NEVER return "line": null.
5. NEVER invent a line number — only use numbers that appear in the CODE CHANGES.
6. Focus on lines marked [ADDED] as those are newly introduced changes.
7. If an issue cannot be mapped to a specific line, do not include it.
8. In "suggestion", provide the exact replacement code for that line.
9. Return ONLY valid JSON. Do not include any text before or after the JSON object."""
