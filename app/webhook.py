import hmac
import hashlib
import os

from dotenv import load_dotenv
from fastapi import Request, HTTPException

load_dotenv()

GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")


async def verify_webhook_signature(request: Request) -> bytes:
    """Verify the GitHub webhook HMAC-SHA256 signature.

    Returns the raw body on success; raises 403 on mismatch.
    """
    if not GITHUB_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="GITHUB_WEBHOOK_SECRET is not configured")

    body = await request.body()

    signature_header = request.headers.get("X-Hub-Signature-256")
    if not signature_header:
        raise HTTPException(status_code=403, detail="Missing X-Hub-Signature-256 header")

    expected = "sha256=" + hmac.new(
        GITHUB_WEBHOOK_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(status_code=403, detail="Invalid webhook signature")

    return body
