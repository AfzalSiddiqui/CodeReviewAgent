import os

# app.github raises at import time without a token; tests never call GitHub.
os.environ.setdefault("GITHUB_TOKEN", "test-token")
os.environ.setdefault("GITHUB_WEBHOOK_SECRET", "test-secret")
