from fastapi import FastAPI

app = FastAPI(title="GitHub PR Review Agent")


@app.get("/")
def home():
    return {
        "message": "GitHub PR Review Agent is running"
    }


@app.post("/review-pr")
def review_pr():
    return {
        "message": "PR review coming soon"
    }
