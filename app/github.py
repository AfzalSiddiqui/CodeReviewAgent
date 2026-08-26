import os
import httpx
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
if not GITHUB_TOKEN:
    raise RuntimeError("GITHUB_TOKEN environment variable is not set")

GITHUB_API = "https://api.github.com"

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}


def get_pull_request(owner: str, repo: str, pr_number: int) -> dict:
    url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}"
    response = httpx.get(url, headers=HEADERS)
    response.raise_for_status()
    return response.json()


def get_pull_request_files(owner: str, repo: str, pr_number: int) -> list:
    url = f"{GITHUB_API}/repos/{owner}/{repo}/pulls/{pr_number}/files"
    response = httpx.get(url, headers=HEADERS)
    response.raise_for_status()
    return response.json()


def get_file_content(owner: str, repo: str, path: str, ref: str) -> str:
    """Fetch raw file content from GitHub at a specific ref/SHA."""
    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"
    response = httpx.get(
        url,
        headers={**HEADERS, "Accept": "application/vnd.github.raw+json"},
        params={"ref": ref},
        timeout=30,
    )
    response.raise_for_status()
    return response.text


def get_repo_tree(owner: str, repo: str, ref: str) -> list:
    """List files in the repo tree (for finding related files)."""
    url = f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{ref}"
    response = httpx.get(
        url,
        headers=HEADERS,
        params={"recursive": "1"},
        timeout=30,
    )
    response.raise_for_status()
    tree = response.json().get("tree", [])
    return [item["path"] for item in tree if item["type"] == "blob"]
