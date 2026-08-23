import httpx

from app.github import GITHUB_API, HEADERS


def create_pull_request_comment(
    owner: str,
    repo: str,
    pr_number: int,
    body: str
):
    url = (
        f"{GITHUB_API}/repos/"
        f"{owner}/{repo}/issues/{pr_number}/comments"
    )

    response = httpx.post(
        url,
        headers=HEADERS,
        json={
            "body": body
        },
        timeout=30
    )

    response.raise_for_status()

    return response.json()


def parse_valid_lines(patch: str) -> set[int]:
    """Extract valid NEW-side line numbers from a unified diff patch."""
    valid = set()
    new_line = 0

    for raw in patch.split("\n"):
        if raw.startswith("@@"):
            parts = raw.split("+")[1].split("@@")[0].strip()
            if "," in parts:
                new_line = int(parts.split(",")[0])
            else:
                new_line = int(parts)
            continue

        if new_line == 0:
            continue

        if raw.startswith("-"):
            continue

        valid.add(new_line)
        new_line += 1

    return valid


def parse_diff_lines(patch: str) -> list[dict]:
    """Parse a unified diff patch into structured lines.

    Returns a list of dicts with keys:
      - line: the NEW-side line number
      - type: "added" or "context"
      - content: the source code text
    Only new-side lines (added / context) are returned — these are
    the lines GitHub accepts for review comments with side=RIGHT.
    """
    result = []
    new_line = 0

    for raw in patch.split("\n"):
        if raw.startswith("@@"):
            parts = raw.split("+")[1].split("@@")[0].strip()
            if "," in parts:
                new_line = int(parts.split(",")[0])
            else:
                new_line = int(parts)
            continue

        if new_line == 0:
            continue

        if raw.startswith("-"):
            # Deleted line — skip, not in new file
            continue

        line_type = "added" if raw.startswith("+") else "context"
        content = raw[1:] if raw.startswith("+") or raw.startswith(" ") else raw

        result.append({
            "line": new_line,
            "type": line_type,
            "content": content,
        })
        new_line += 1

    return result


def dismiss_pending_reviews(owner: str, repo: str, pr_number: int):
    """Dismiss any pending reviews on the PR for the authenticated user.

    GitHub only allows one pending review per user per PR.  If a
    previous review was left in PENDING state (e.g. a failed attempt),
    it blocks all new reviews and individual comments.
    """
    url = (
        f"{GITHUB_API}/repos/"
        f"{owner}/{repo}/pulls/{pr_number}/reviews"
    )

    response = httpx.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()

    for review in response.json():
        if review.get("state") == "PENDING":
            review_id = review["id"]
            print(f"Dismissing pending review {review_id}...")

            # Delete the pending review (DELETE removes it entirely)
            delete_url = (
                f"{GITHUB_API}/repos/"
                f"{owner}/{repo}/pulls/{pr_number}/reviews/{review_id}"
            )
            del_resp = httpx.delete(
                delete_url, headers=HEADERS, timeout=30
            )
            print(f"  DELETE {review_id} -> {del_resp.status_code}")


def create_pull_request_review(
    owner: str,
    repo: str,
    pr_number: int,
    body: str,
    commit_id: str,
    comments: list[dict],
):
    """Create a single review with multiple inline comments.

    Each entry in *comments* should have keys: path, line, body.
    """
    url = (
        f"{GITHUB_API}/repos/"
        f"{owner}/{repo}/pulls/{pr_number}/reviews"
    )

    review_comments = [
        {
            "path": c["path"],
            "line": c["line"],
            "side": "RIGHT",
            "body": c["body"],
        }
        for c in comments
    ]

    response = httpx.post(
        url,
        headers=HEADERS,
        json={
            "commit_id": commit_id,
            "body": body,
            "event": "COMMENT",
            "comments": review_comments,
        },
        timeout=30,
    )

    print("GITHUB STATUS:", response.status_code)
    print("GITHUB RESPONSE:", response.text)

    response.raise_for_status()

    return response.json()


def create_review_comment(
    owner: str,
    repo: str,
    pr_number: int,
    commit_id: str,
    path: str,
    line: int,
    body: str,
):
    """Post a single inline review comment on a pull request."""
    url = (
        f"{GITHUB_API}/repos/"
        f"{owner}/{repo}/pulls/{pr_number}/comments"
    )

    response = httpx.post(
        url,
        headers=HEADERS,
        json={
            "commit_id": commit_id,
            "path": path,
            "line": line,
            "side": "RIGHT",
            "body": body,
        },
        timeout=30,
    )

    print(f"COMMENT on {path}:{line} -> {response.status_code}")
    if not response.is_success:
        print(f"  RESPONSE: {response.text}")

    response.raise_for_status()

    return response.json()
