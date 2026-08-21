from fastapi import FastAPI, HTTPException
from app.github import get_pull_request, get_pull_request_files
import httpx

app = FastAPI(title="GitHub PR Review Agent")


@app.get("/")
def home():
    return {
        "message": "GitHub PR Review Agent is running"
    }


@app.get("/review-pr")
def review_pr(owner: str, repo: str, pr_number: int):
    try:
        pr = get_pull_request(owner, repo, pr_number)
        files = get_pull_request_files(owner, repo, pr_number)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {str(e)}")

    return {
        "pr_title": pr.get("title"),
        "pr_state": pr.get("state"),
        "changed_files": [
            {
                "filename": f.get("filename"),
                "status": f.get("status"),
                "patch": f.get("patch"),
            }
            for f in files
        ],
    }
