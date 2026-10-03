import hashlib
import hmac

import pytest
from fastapi import HTTPException

from app import webhook

SECRET = "test-secret"


class FakeRequest:
    def __init__(self, body: bytes, headers: dict):
        self._body = body
        self.headers = headers

    async def body(self):
        return self._body


def sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture(autouse=True)
def secret(monkeypatch):
    monkeypatch.setattr(webhook, "GITHUB_WEBHOOK_SECRET", SECRET)


async def test_valid_signature_returns_body():
    body = b'{"action": "opened"}'
    req = FakeRequest(body, {"X-Hub-Signature-256": sign(body)})
    assert await webhook.verify_webhook_signature(req) == body


async def test_missing_signature_is_rejected():
    with pytest.raises(HTTPException) as exc:
        await webhook.verify_webhook_signature(FakeRequest(b"{}", {}))
    assert exc.value.status_code == 403


async def test_tampered_body_is_rejected():
    req = FakeRequest(b'{"action": "closed"}', {"X-Hub-Signature-256": sign(b'{"action": "opened"}')})
    with pytest.raises(HTTPException) as exc:
        await webhook.verify_webhook_signature(req)
    assert exc.value.status_code == 403


async def test_missing_secret_is_a_server_error(monkeypatch):
    monkeypatch.setattr(webhook, "GITHUB_WEBHOOK_SECRET", "")
    with pytest.raises(HTTPException) as exc:
        await webhook.verify_webhook_signature(FakeRequest(b"{}", {}))
    assert exc.value.status_code == 500
