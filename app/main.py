import json
import logging

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.agent import Orchestrator
from app.rag import VectorStore
from app.webhook import verify_webhook_signature

logger = logging.getLogger(__name__)

app = FastAPI(title="CodeReviewAgent")

orchestrator = Orchestrator()
vector_store = orchestrator.vector_store


# ── Request models ────────────────────────────────────────────────


class PolicyRequest(BaseModel):
    id: str
    text: str
    metadata: dict | None = None


class BulkPolicyRequest(BaseModel):
    policies: list[PolicyRequest]


class SearchRequest(BaseModel):
    query: str
    n_results: int = 3
    category_filter: str | None = None


# ── Endpoints ─────────────────────────────────────────────────────


@app.get("/")
def home():
    return {
        "message": "CodeReviewAgent is running"
    }


@app.get("/review-policy")
def review_policy():
    return {
        "categories": orchestrator.policy.get_categories(),
        "checks": orchestrator.policy.get_checks(),
        "agents": {
            name: orchestrator.policy.get_agent_config(name)
            for name in orchestrator.policy.get_enabled_agents()
        },
    }


@app.post("/review-pr")
async def review_pr(owner: str, repo: str, pr_number: int):
    return await orchestrator.review(owner, repo, pr_number)


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
            background_tasks.add_task(
                orchestrator.review_safe, owner, repo, pr_number,
            )

            return JSONResponse(
                content={"message": "Review scheduled"},
                status_code=202,
            )

    # 4. Ignore all other events
    return {"message": "Event ignored"}


# ── RAG Endpoints ─────────────────────────────────────────────────


@app.post("/rag/policies")
def add_policy(req: PolicyRequest):
    vector_store.add_policy(
        policy_id=req.id,
        text=req.text,
        metadata=req.metadata,
    )
    return {"status": "ok", "id": req.id}


@app.post("/rag/policies/bulk")
def add_policies_bulk(req: BulkPolicyRequest):
    policies = [
        {"id": p.id, "text": p.text, "metadata": p.metadata or {}}
        for p in req.policies
    ]
    vector_store.add_policies_bulk(policies)
    return {"status": "ok", "count": len(policies)}


@app.get("/rag/policies/count")
def policies_count():
    return {"count": vector_store.count()}


@app.post("/rag/search")
def rag_search(req: SearchRequest):
    results = vector_store.search(
        query=req.query,
        n_results=req.n_results,
        category_filter=req.category_filter,
    )
    return results
