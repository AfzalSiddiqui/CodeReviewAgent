from fastapi import FastAPI

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


app = FastAPI(title="GitHub PR Review Agent")

policy = ReviewPolicy()
ai_reviewer = AIReviewer()


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

    # 1. Get PR information
    pr = get_pull_request(
        owner,
        repo,
        pr_number
    )

    # 2. Get changed files
    files = get_pull_request_files(
        owner,
        repo,
        pr_number
    )

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
            print(
                f"Skipping finding: line {line} not in diff for {file_path}"
                f" (valid: {sorted(valid)[:20]})"
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
            print(f"Batch review failed: {e}")
            print("Falling back to individual comments...")

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
                    print(
                        f"Skipping comment {c['path']}:{c['line']}: {ce}"
                    )

            print(f"Posted {posted}/{len(review_comments)} inline comments")

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
