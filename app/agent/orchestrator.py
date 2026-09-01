import asyncio
import logging

from app.agent.review_policy import ReviewPolicy
from app.agent.security_agent import SecurityAgent
from app.agent.logic_bug_agent import LogicBugAgent
from app.agent.performance_agent import PerformanceAgent
from app.agent.code_quality_agent import CodeQualityAgent
from app.agent.test_coverage_agent import TestCoverageAgent
from app.agent.dependency_agent import DependencyAgent
from app.agent.summary_agent import SummaryAgent
from app.rag.vector_store import VectorStore
from app.github import get_pull_request, get_pull_request_files, get_file_content
from app.github_comments import (
    create_pull_request_review,
    create_pull_request_comment,
    create_review_comment,
    dismiss_pending_reviews,
    parse_diff_lines,
)

logger = logging.getLogger(__name__)

AGENT_CLASSES = [
    SecurityAgent,
    LogicBugAgent,
    PerformanceAgent,
    CodeQualityAgent,
    TestCoverageAgent,
    DependencyAgent,
]


class Orchestrator:
    """Multi-agent orchestrator that fans out reviews to specialized agents."""

    def __init__(self):
        self.policy = ReviewPolicy()
        self.vector_store = VectorStore()
        self.summary_agent = SummaryAgent(self.policy)

        # Instantiate only enabled review agents
        enabled = set(self.policy.get_enabled_agents())
        self.agents = []
        for cls in AGENT_CLASSES:
            agent = cls(self.policy, self.vector_store)
            if agent.name in enabled:
                self.agents.append(agent)

    # ── Public API ──────────────────────────────────────────────────

    async def review(self, owner: str, repo: str, pr_number: int) -> dict:
        """Run the full multi-agent review pipeline."""

        # Step 1: Gather context
        pr = get_pull_request(owner, repo, pr_number)
        files = get_pull_request_files(owner, repo, pr_number)
        structured_diff, valid_lines = self._build_diff(files)

        if not structured_diff.strip():
            return self._build_result(pr, files, {
                "summary": "No code changes to review.",
                "risk_level": "LOW",
                "findings": [],
                "recommendations": [],
            }, {})

        # Step 2: Fan-out all review agents in parallel
        agent_stats = {}

        tasks = [agent.review(structured_diff) for agent in self.agents]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_findings = []
        for agent, result in zip(self.agents, results):
            if isinstance(result, Exception):
                logger.error("[%s] agent failed: %s", agent.name, result)
                agent_stats[agent.name] = {"status": "error", "findings": 0}
                continue

            findings = result.get("findings", [])
            agent_stats[agent.name] = {"status": "ok", "findings": len(findings)}
            all_findings.extend(findings)

        # Step 3: Merge & deduplicate
        merged = self._deduplicate(all_findings)

        # Step 4: Validate findings (before summary so it only sees real findings)
        validated = self._validate_findings(merged, valid_lines)

        # Step 5: Summary agent
        summary_result = await self.summary_agent.summarize(validated, structured_diff)

        # Step 6: Enrich HIGH/CRITICAL findings
        enriched = self._enrich_findings(validated, owner, repo, pr)

        # Step 7: Build comments with agent labels
        comments = self._build_comments(enriched)

        # Step 8: Post to GitHub
        ai_result = {
            "summary": summary_result.get("summary", ""),
            "risk_level": summary_result.get("risk_level", "LOW"),
            "findings": enriched,
            "recommendations": summary_result.get("recommendations", []),
            "key_concerns": summary_result.get("key_concerns", []),
        }
        self._post_review(owner, repo, pr_number, pr, ai_result, comments)

        # Step 9: Return result with agent_stats
        return self._build_result(pr, files, ai_result, agent_stats)

    async def review_safe(self, owner: str, repo: str, pr_number: int) -> None:
        """Wrapper that catches and logs exceptions — safe for background tasks."""
        try:
            logger.info("Starting review for %s/%s#%d", owner, repo, pr_number)
            await self.review(owner, repo, pr_number)
            logger.info("Review completed for %s/%s#%d", owner, repo, pr_number)
        except Exception:
            logger.exception("Review failed for %s/%s#%d", owner, repo, pr_number)

    # ── Step 1: Gather context ──────────────────────────────────────

    def _build_diff(self, files: list) -> tuple[str, dict[str, set[int]]]:
        """Build a structured diff string and valid-lines map from PR files."""
        structured_diff = ""
        valid_lines_by_file: dict[str, set[int]] = {}

        for file in files:
            patch = file.get("patch")
            if not patch:
                continue

            diff_lines = parse_diff_lines(patch)
            valid_lines_by_file[file["filename"]] = {
                dl["line"] for dl in diff_lines
            }

            structured_diff += f"\nFILE: {file['filename']}\n"

            for dl in diff_lines:
                tag = "[ADDED]" if dl["type"] == "added" else "[CONTEXT]"
                structured_diff += (
                    f"  {dl['line']} | {tag} {dl['content']}\n"
                )

            structured_diff += "--------------------------------\n"

        return structured_diff, valid_lines_by_file

    # ── Step 3: Deduplicate ─────────────────────────────────────────

    def _deduplicate(self, findings: list[dict]) -> list[dict]:
        """Deduplicate findings by (file, line, category), keeping higher severity."""
        severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
        seen: dict[tuple, dict] = {}

        for finding in findings:
            key = (
                finding.get("file", ""),
                finding.get("line", 0),
                finding.get("category", ""),
            )
            existing = seen.get(key)
            if existing:
                existing_sev = severity_order.get(existing.get("severity", "LOW").upper(), 1)
                new_sev = severity_order.get(finding.get("severity", "LOW").upper(), 1)
                if new_sev > existing_sev:
                    seen[key] = finding
            else:
                seen[key] = finding

        return list(seen.values())

    # ── Step 5: Validate findings ───────────────────────────────────

    def _validate_findings(
        self,
        findings: list[dict],
        valid_lines: dict[str, set[int]],
    ) -> list[dict]:
        """Drop findings that reference invalid files or lines."""
        validated = []

        for finding in findings:
            file_path = finding.get("file")
            line = finding.get("line")

            if not file_path:
                logger.info("Dropping finding: missing file path — %s", finding.get("issue", ""))
                continue

            if not line:
                logger.info("Dropping finding: null/missing line — %s:%s", file_path, finding.get("issue", ""))
                continue

            if file_path not in valid_lines:
                logger.info("Dropping finding: file %s not in changed files", file_path)
                continue

            valid = valid_lines[file_path]
            if line not in valid:
                logger.info(
                    "Dropping finding: line %d not in diff for %s (valid: %s)",
                    line, file_path, sorted(valid)[:20],
                )
                continue

            validated.append(finding)

        dropped = len(findings) - len(validated)
        if dropped:
            logger.info("Validation: kept %d findings, dropped %d", len(validated), dropped)

        return validated

    # ── Step 6: Enrich findings ─────────────────────────────────────

    def _enrich_findings(
        self,
        findings: list[dict],
        owner: str,
        repo: str,
        pr: dict,
    ) -> list[dict]:
        """For HIGH/CRITICAL findings, fetch full file content for context."""
        ref = pr["head"]["sha"]

        for finding in findings:
            severity = finding.get("severity", "").upper()
            if severity not in ("HIGH", "CRITICAL"):
                continue

            file_path = finding.get("file")
            if not file_path:
                continue

            try:
                content = get_file_content(owner, repo, file_path, ref)
                lines = content.splitlines()
                line_num = finding.get("line", 1)

                start = max(0, line_num - 11)
                end = min(len(lines), line_num + 10)
                context_lines = lines[start:end]

                finding["full_context"] = "\n".join(
                    f"{start + i + 1} | {l}" for i, l in enumerate(context_lines)
                )
            except Exception as e:
                logger.warning("Could not fetch file context for %s: %s", file_path, e)

        return findings

    # ── Step 7: Build comments ──────────────────────────────────────

    def _build_comments(self, findings: list[dict]) -> list[dict]:
        """Convert validated findings into GitHub review comment dicts."""
        comments = []

        for finding in findings:
            agent_label = finding.get("agent", "unknown")
            suggestion = finding.get("suggestion", "")
            comment_body = (
                f"**[{agent_label}]** "
                f"**Severity:** {finding['severity']}\n\n"
                f"**Issue:** {finding['issue']}\n\n"
                f"**Recommendation:** {finding['recommendation']}"
            )
            if suggestion:
                comment_body += (
                    f"\n\n**Suggested change:**\n```suggestion\n"
                    f"{suggestion}\n```"
                )

            comments.append({
                "path": finding["file"],
                "line": finding["line"],
                "body": comment_body,
            })

        return comments

    # ── Step 8: Post review ─────────────────────────────────────────

    def _post_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        pr: dict,
        ai_result: dict,
        comments: list[dict],
    ) -> None:
        """Dismiss pending reviews and post comments to GitHub."""
        commit_id = pr["head"]["sha"]
        dismiss_pending_reviews(owner, repo, pr_number)

        if not comments:
            return

        summary = f"\U0001f916 **AI Code Review** \u2014 {ai_result.get('summary', '')}"

        try:
            create_pull_request_review(
                owner, repo, pr_number,
                body=summary,
                commit_id=commit_id,
                comments=comments,
            )
        except Exception as e:
            logger.warning("Batch review failed: %s", e)
            logger.info("Falling back to individual comments...")

            posted = 0
            for c in comments:
                try:
                    create_review_comment(
                        owner, repo, pr_number,
                        commit_id=commit_id,
                        path=c["path"],
                        line=c["line"],
                        body=c["body"],
                    )
                    posted += 1
                except Exception as ce:
                    logger.warning("Skipping comment %s:%s: %s", c["path"], c["line"], ce)

            logger.info("Posted %d/%d inline comments", posted, len(comments))

            create_pull_request_comment(
                owner, repo, pr_number, body=summary,
            )

    # ── Step 9: Build result ────────────────────────────────────────

    def _build_result(
        self, pr: dict, files: list, ai_result: dict, agent_stats: dict
    ) -> dict:
        return {
            "number": pr["number"],
            "title": pr["title"],
            "author": pr["user"]["login"],
            "state": pr["state"],
            "url": pr["html_url"],
            "ai_review": ai_result,
            "agent_stats": agent_stats,
            "files": [
                {
                    "filename": file["filename"],
                    "status": file["status"],
                    "additions": file["additions"],
                    "deletions": file["deletions"],
                    "changes": file["changes"],
                    "patch": file.get("patch"),
                }
                for file in files
            ],
        }
