import logging

from app.agent.review_policy import ReviewPolicy
from app.ai_reviewer import AIReviewer
from app.github import get_pull_request, get_pull_request_files, get_file_content
from app.github_comments import (
    create_pull_request_review,
    create_pull_request_comment,
    create_review_comment,
    dismiss_pending_reviews,
    parse_diff_lines,
)

logger = logging.getLogger(__name__)


class PRReviewAgent:
    """Agent that orchestrates the full PR review flow.

    Steps: gather context -> AI review -> validate findings ->
    enrich high-severity findings -> build comments -> post to GitHub.
    """

    def __init__(self):
        self.policy = ReviewPolicy()
        self.ai = AIReviewer()

    # ── Public API ──────────────────────────────────────────────────

    def review(self, owner: str, repo: str, pr_number: int) -> dict:
        """Run the full review pipeline and return the result."""

        # Step 1: Gather context
        pr = self._get_pr(owner, repo, pr_number)
        files = self._get_files(owner, repo, pr_number)
        structured_diff, valid_lines = self._build_diff(files)

        # Step 2: AI review
        ai_result = self.ai.review(structured_diff, self.policy.get_checks())

        # Step 3: Validate findings (strict)
        validated = self._validate_findings(ai_result, valid_lines)

        # Step 4: Enrich — for HIGH/CRITICAL, fetch full file context
        enriched = self._enrich_findings(validated, owner, repo, pr)

        # Step 5: Build comments
        comments = self._build_comments(enriched)

        # Step 6: Post to GitHub
        self._post_review(owner, repo, pr_number, pr, ai_result, comments)

        # Step 7: Return result
        return self._build_result(pr, files, ai_result)

    def review_safe(self, owner: str, repo: str, pr_number: int) -> None:
        """Wrapper that catches and logs exceptions — safe for background tasks."""
        try:
            logger.info("Starting review for %s/%s#%d", owner, repo, pr_number)
            self.review(owner, repo, pr_number)
            logger.info("Review completed for %s/%s#%d", owner, repo, pr_number)
        except Exception:
            logger.exception("Review failed for %s/%s#%d", owner, repo, pr_number)

    # ── Step 1: Gather context ──────────────────────────────────────

    def _get_pr(self, owner: str, repo: str, pr_number: int) -> dict:
        return get_pull_request(owner, repo, pr_number)

    def _get_files(self, owner: str, repo: str, pr_number: int) -> list:
        return get_pull_request_files(owner, repo, pr_number)

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

    # ── Step 3: Validate findings ───────────────────────────────────

    def _validate_findings(
        self,
        ai_result: dict,
        valid_lines: dict[str, set[int]],
    ) -> list[dict]:
        """Drop findings that reference invalid files or lines."""
        validated = []

        for finding in ai_result.get("findings", []):
            file_path = finding.get("file")
            line = finding.get("line")

            # Drop: missing file
            if not file_path:
                logger.info("Dropping finding: missing file path — %s", finding.get("issue", ""))
                continue

            # Drop: missing or null line
            if not line:
                logger.info("Dropping finding: null/missing line — %s:%s", file_path, finding.get("issue", ""))
                continue

            # Drop: file not in changed files
            if file_path not in valid_lines:
                logger.info(
                    "Dropping finding: file %s not in changed files", file_path,
                )
                continue

            # Drop: line not in valid diff lines
            valid = valid_lines[file_path]
            if line not in valid:
                logger.info(
                    "Dropping finding: line %d not in diff for %s (valid: %s)",
                    line, file_path, sorted(valid)[:20],
                )
                continue

            validated.append(finding)

        dropped = len(ai_result.get("findings", [])) - len(validated)
        if dropped:
            logger.info(
                "Validation: kept %d findings, dropped %d", len(validated), dropped,
            )

        return validated

    # ── Step 4: Enrich findings ─────────────────────────────────────

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

                # Extract surrounding context (10 lines before/after)
                start = max(0, line_num - 11)
                end = min(len(lines), line_num + 10)
                context_lines = lines[start:end]

                finding["full_context"] = "\n".join(
                    f"{start + i + 1} | {l}" for i, l in enumerate(context_lines)
                )
            except Exception as e:
                logger.warning(
                    "Could not fetch file context for %s: %s", file_path, e,
                )

        return findings

    # ── Step 5: Build comments ──────────────────────────────────────

    def _build_comments(self, findings: list[dict]) -> list[dict]:
        """Convert validated findings into GitHub review comment dicts."""
        comments = []

        for finding in findings:
            suggestion = finding.get("suggestion", "")
            comment_body = (
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

    # ── Step 6: Post review ─────────────────────────────────────────

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

        # Try batch review first
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
                    logger.warning(
                        "Skipping comment %s:%s: %s", c["path"], c["line"], ce,
                    )

            logger.info("Posted %d/%d inline comments", posted, len(comments))

            create_pull_request_comment(
                owner, repo, pr_number, body=summary,
            )

    # ── Step 7: Build result ────────────────────────────────────────

    def _build_result(self, pr: dict, files: list, ai_result: dict) -> dict:
        return {
            "number": pr["number"],
            "title": pr["title"],
            "author": pr["user"]["login"],
            "state": pr["state"],
            "url": pr["html_url"],
            "ai_review": ai_result,
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
