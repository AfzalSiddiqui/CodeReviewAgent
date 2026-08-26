import json
import logging

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse

from app.agent import PRReviewAgent
from app.webhook import verify_webhook_signature

logger = logging.getLogger(__name__)

app = FastAPI(title="CodeReviewAgent")

agent = PRReviewAgent()


# ── Endpoints ───────────────────────────────────────────────────────────


@app.get("/")
def home():
    return {
        "message": "CodeReviewAgent is running"
    }


@app.get("/review-policy")
def review_policy():
    return {
        "categories": agent.policy.get_categories(),
        "checks": agent.policy.get_checks()
    }


@app.post("/review-pr")
def review_pr(owner: str, repo: str, pr_number: int):
    return agent.review(owner, repo, pr_number)


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
            background_tasks.add_task(agent.review_safe, owner, repo, pr_number)

            return JSONResponse(
                content={"message": "Review scheduled"},
                status_code=202,
            )

    # 4. Ignore all other events
    return {"message": "Event ignored"}
