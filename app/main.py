import json
import logging

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse

from app.github import get_pull_request, get_pull_request_files
from app.agent import ReviewPolicy
from app.ai_reviewer import AIReviewer
from app.github_comments import (
    create_pull_request_review,
    create_pull_request_comment,
    create_review_comment,
    dismiss_pending_reviews,
    parse_diff_lines,
    parse_valid_lines,
)
from app.webhook import verify_webhook_signature

logger = logging.getLogger(__name__)

app = FastAPI(title="GitHub PR Review Agent")

policy = ReviewPolicy()
ai_reviewer = AIReviewer()


def run_review(owner: str, repo: str, pr_number: int) -> dict:
    """Core review logic shared by the manual endpoint and the webhook."""

    # 1. Get PR information
    pr = get_pull_request(owner, repo, pr_number)

    # 2. Get changed files
    files = get_pull_request_files(owner, repo, pr_number)

    # 3. Build structured diff with explicit line numbers
    #    so the AI can only reference lines we know are valid.
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

    # 4. Ask AI to review the diff
    ai_review = ai_reviewer.review(
        structured_diff,
        policy.get_checks()
    )

    # 5. Get PR commit SHA
    commit_id = pr["head"]["sha"]

    # 6. Collect inline comments, skipping invalid lines
    review_comments: list[dict] = []

    for finding in ai_review.get("findings", []):
        file_path = finding.get("file")
        line = finding.get("line")

        if not file_path or not line:
            continue

        # Validate that the line actually exists in the diff
        valid = valid_lines_by_file.get(file_path, set())
        if line not in valid:
            logger.info(
                "Skipping finding: line %d not in diff for %s (valid: %s)",
                line, file_path, sorted(valid)[:20],
            )
            continue

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

        review_comments.append({
            "path": file_path,
            "line": line,
            "body": comment_body,
        })

    # 7. Clear any stuck pending reviews, then post inline comments
    dismiss_pending_reviews(owner, repo, pr_number)

    if review_comments:
        # Try batch review first
        try:
            create_pull_request_review(
                owner,
                repo,
                pr_number,
                body=f"🤖 **AI Code Review** — {ai_review.get('summary', '')}",
                commit_id=commit_id,
                comments=review_comments,
            )
        except Exception as e:
            logger.warning("Batch review failed: %s", e)
            logger.info("Falling back to individual comments...")

            # Fall back: post each comment individually, skip failures
            posted = 0
            for c in review_comments:
                try:
                    create_review_comment(
                        owner,
                        repo,
                        pr_number,
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

            logger.info("Posted %d/%d inline comments", posted, len(review_comments))

            # Post the summary as a general PR comment
            create_pull_request_comment(
                owner,
                repo,
                pr_number,
                body=f"🤖 **AI Code Review** — {ai_review.get('summary', '')}",
            )

    # 8. Return review result
    return {
        "number": pr["number"],
        "title": pr["title"],
        "author": pr["user"]["login"],
        "state": pr["state"],
        "url": pr["html_url"],
        "ai_review": ai_review,
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


def run_review_safe(owner: str, repo: str, pr_number: int) -> None:
    """Wrapper that catches and logs exceptions — safe for background tasks."""
    try:
        logger.info("Starting review for %s/%s#%d", owner, repo, pr_number)
        run_review(owner, repo, pr_number)
        logger.info("Review completed for %s/%s#%d", owner, repo, pr_number)
    except Exception:
        logger.exception("Review failed for %s/%s#%d", owner, repo, pr_number)


# ── Endpoints ───────────────────────────────────────────────────────────


@app.get("/")
def home():
    return {
        "message": "GitHub PR Review Agent is running"
    }


@app.get("/review-policy")
def review_policy():
    return {
        "categories": policy.get_categories(),
        "checks": policy.get_checks()
    }


@app.post("/review-pr")
def review_pr(owner: str, repo: str, pr_number: int):
    return run_review(owner, repo, pr_number)


@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    # 1. Verify HMAC signature
    body = await verify_webhook_signature(request)
    payload = json.loads(body)

    # 2. Handle ping event (GitHub sends this when the webhook is first configured)
    event = request.headers.get("X-GitHub-Event", "")

    if event == "ping":
        return {"message": "pong"}

    # 3. Handle pull_request events
    if event == "pull_request":
        action = payload.get("action")
        if action in ("opened", "synchronize", "reopened"):
            repo_info = payload["repository"]
            owner = repo_info["owner"]["login"]
            repo = repo_info["name"]
            pr_number = payload["pull_request"]["number"]

            logger.info(
                "Webhook: scheduling review for %s/%s#%d (action=%s)",
                owner, repo, pr_number, action,
            )
            background_tasks.add_task(run_review_safe, owner, repo, pr_number)

            return JSONResponse(
                content={"message": "Review scheduled"},
                status_code=202,
            )

    # 4. Ignore all other events
    return {"message": "Event ignored"}
