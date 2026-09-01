
# CodeReviewAgent

Automated GitHub Pull Request code review system powered by local LLMs via [Ollama](https://ollama.com). Uses a **multi-agent architecture** where 7 specialized agents review code in parallel, each with a focused prompt and configurable model, producing higher-quality findings than a single monolithic review.

The point is not to replace human review. It handles the mechanical layer -- conventions, missed edge cases, patterns a team has already agreed on -- so reviewers spend their attention on design and correctness.

---

## Architecture

```
Webhook / API
     |
     v
Orchestrator
     |
     +---> [1] Gather context (GitHub API: PR, files, diff)
     |
     +---> [2] Fan-out 6 review agents in parallel (asyncio.gather)
     |          |
     |          +-- SecurityAgent      (qwen2.5-coder:14b)
     |          +-- LogicBugAgent      (qwen2.5-coder:14b)
     |          +-- PerformanceAgent   (qwen2.5-coder:7b)
     |          +-- CodeQualityAgent   (qwen2.5-coder:7b)
     |          +-- TestCoverageAgent  (qwen2.5-coder:7b)
     |          +-- DependencyAgent    (qwen2.5-coder:7b)
     |
     +---> [3] Merge & deduplicate findings
     +---> [4] Validate (drop hallucinated file/line references)
     +---> [5] SummaryAgent synthesizes overall assessment
     +---> [6] Enrich HIGH/CRITICAL findings with full file context
     +---> [7] Build GitHub review comments with [agent_name] labels
     +---> [8] Post to GitHub (batch review, fallback to individual)
     +---> [9] Return result with agent_stats
```

Each agent queries the **RAG vector store** (ChromaDB) for repository-specific policies before building its prompt, so reviews adapt to your team's standards.

---

## Agents

| Agent | Model | Focus |
|-------|-------|-------|
| **SecurityAgent** | 14b | Secrets, injection, auth, OWASP Top 10 |
| **LogicBugAgent** | 14b | Off-by-one, null refs, edge cases, wrong operators |
| **PerformanceAgent** | 7b | O(n^2), memory, N+1 queries, blocking I/O |
| **CodeQualityAgent** | 7b | Readability, SRP, naming, deprecated APIs, logging |
| **TestCoverageAgent** | 7b | Missing tests, weak assertions, untested error paths |
| **DependencyAgent** | 7b | Imports, version conflicts, unused/vulnerable packages |
| **SummaryAgent** | 7b | Synthesizes findings into overall risk assessment |

Models are configurable per-agent in `policies/default.yaml`. Security and Logic use the larger 14b model for higher accuracy on critical concerns.

---

## Why the Policy Layer Is Separate

Most review bots hard-code their rules. That makes the rules invisible to the people they govern, and it means changing a standard requires a code change and a redeploy.

Here, review standards live in `policies/`, entirely outside the application code in `app/`. This has three consequences:

- **Rules are readable by non-authors.** A tech lead or security reviewer can read `policies/` without reading Python.
- **Rules are versioned independently.** Every change to a standard is a diff with an author and a date -- an audit trail of how the team's engineering standards evolved.
- **Rules change without redeploying.** Updating a policy is a config change, not a release.

---

## Project Structure

```
app/
  agent/
    orchestrator.py          # Multi-agent orchestrator (main pipeline)
    base_agent.py            # Abstract base class for review agents
    security_agent.py        # Security specialist
    logic_bug_agent.py       # Logic/correctness specialist
    performance_agent.py     # Performance specialist
    code_quality_agent.py    # Code quality specialist
    test_coverage_agent.py   # Test coverage specialist
    dependency_agent.py      # Dependency specialist
    summary_agent.py         # Summary synthesizer
    review_policy.py         # YAML policy loader with agent config
    utils.py                 # Shared utilities (extract_json)
  rag/
    vector_store.py          # ChromaDB vector store for RAG
  main.py                    # FastAPI application and endpoints
  github.py                  # GitHub API client
  github_comments.py         # GitHub review comment management
  webhook.py                 # Webhook signature verification
policies/
  default.yaml               # Review categories, checks, and agent config
```

---

## Prerequisites

- **Python 3.11+**
- **Ollama** installed and running locally
- Required Ollama models pulled:
  ```bash
  ollama pull qwen2.5-coder:7b
  ollama pull qwen2.5-coder:14b
  ```
- **GitHub Token** with repo access

---

## Getting Started

1. **Clone the repository:**
   ```bash
   git clone https://github.com/AfzalSiddiqui/CodeReviewAgent.git
   cd CodeReviewAgent
   ```

2. **Create a virtual environment and install dependencies:**
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure environment variables:**

   Create a `.env` file in the project root:
   ```
   GITHUB_TOKEN=ghp_your_token_here
   GITHUB_WEBHOOK_SECRET=your_webhook_secret
   ```

4. **Start the server:**
   ```bash
   uvicorn app.main:app --reload
   ```

---

## API Endpoints

### Core

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Health check |
| `GET` | `/review-policy` | Returns active categories, checks, and agent configs |
| `POST` | `/review-pr` | Trigger a review (query params: `owner`, `repo`, `pr_number`) |
| `POST` | `/webhook` | GitHub webhook receiver for PR events |

### RAG (Vector Store)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/rag/policies` | Add a single policy document |
| `POST` | `/rag/policies/bulk` | Add multiple policy documents |
| `GET` | `/rag/policies/count` | Get the number of stored policies |
| `POST` | `/rag/search` | Search policies by query text |

---

## Usage

### Manual PR Review

```bash
curl -X POST "http://localhost:8000/review-pr?owner=myorg&repo=myrepo&pr_number=42"
```

Response includes:

```json
{
  "number": 42,
  "title": "Add payment processing",
  "author": "dev",
  "ai_review": {
    "summary": "Found 3 issues, 1 critical security concern.",
    "risk_level": "HIGH",
    "findings": [...],
    "key_concerns": ["Hardcoded API key in source"],
    "recommendations": ["Move secrets to environment variables"]
  },
  "agent_stats": {
    "security":      { "status": "ok", "findings": 1 },
    "logic_bug":     { "status": "ok", "findings": 1 },
    "performance":   { "status": "ok", "findings": 0 },
    "code_quality":  { "status": "ok", "findings": 1 },
    "test_coverage": { "status": "ok", "findings": 0 },
    "dependency":    { "status": "ok", "findings": 0 }
  },
  "files": [...]
}
```

### GitHub Webhook (Automatic)

Configure a GitHub webhook pointing to `https://your-server/webhook` with:

- **Content type:** `application/json`
- **Secret:** your `GITHUB_WEBHOOK_SECRET` value
- **Events:** Pull requests

Reviews trigger automatically on PR `opened`, `synchronize`, and `reopened` events.

### Adding RAG Policies

Feed repository-specific standards into the vector store so agents incorporate them into reviews:

```bash
# Add a single policy
curl -X POST http://localhost:8000/rag/policies \
  -H "Content-Type: application/json" \
  -d '{
    "id": "sql-injection-policy",
    "text": "All database queries must use parameterized statements. Never concatenate user input into SQL strings.",
    "metadata": {"category": "security"}
  }'

# Add multiple policies at once
curl -X POST http://localhost:8000/rag/policies/bulk \
  -H "Content-Type: application/json" \
  -d '{
    "policies": [
      {
        "id": "error-handling",
        "text": "All public API endpoints must return structured error responses with error codes.",
        "metadata": {"category": "code_quality"}
      },
      {
        "id": "test-coverage",
        "text": "All new endpoints must have integration tests covering success and error paths.",
        "metadata": {"category": "testing"}
      }
    ]
  }'

# Check stored policy count
curl http://localhost:8000/rag/policies/count
```

---

## Configuration

All review behavior is configured in `policies/default.yaml`.

### Review Categories

10 categories with specific checks, each independently enabled/disabled:

| Category | Checks |
|----------|--------|
| code_quality | readability, naming, duplication, complexity |
| logic | incorrect_logic, edge_cases, null_handling, error_handling |
| security | hardcoded_secrets, insecure_data_handling, authentication, authorization, sensitive_data_logging |
| performance | unnecessary_work, memory_usage, network_usage, expensive_operations |
| architecture | separation_of_concerns, single_responsibility, dependency_management |
| testing | unit_tests, edge_case_tests, regression_tests |
| logging | useful_logging, sensitive_data_not_logged |
| modern_practices | deprecated_apis, outdated_patterns, current_framework_practices |
| recommendations | maintainability, scalability, developer_experience |
| dependencies | import_correctness, version_conflicts, unused_dependencies, vulnerable_packages |

### Agent Configuration

Each agent can be enabled/disabled and assigned a specific model:

```yaml
agents:
  security:
    enabled: true
    model: "qwen2.5-coder:14b"
    categories: [security]
  logic_bug:
    enabled: true
    model: "qwen2.5-coder:14b"
    categories: [logic]
  # ...

defaults:
  model: "qwen2.5-coder:7b"
```

To disable an agent or change its model:

```yaml
agents:
  dependency:
    enabled: false              # skip dependency reviews
  security:
    model: "qwen2.5-coder:32b" # upgrade to larger model
```

---

## How It Works

1. A PR event arrives via webhook or manual API call.
2. The **Orchestrator** fetches PR metadata, changed files, and builds a structured diff with exact line numbers.
3. All 6 review agents run **in parallel** via `asyncio.gather`. Each agent:
   - Queries ChromaDB for relevant repository policies (RAG context)
   - Builds a focused prompt with its specific checklist and RAG context
   - Calls Ollama with its configured model (retries up to 2 times on failure)
   - Extracts and parses JSON findings from model output
   - Tags each finding with its agent name
4. Findings are **merged and deduplicated** by `(file, line, category)`, keeping the higher severity on collision.
5. **Validation** drops findings that reference files or lines not present in the actual diff -- filtering out LLM hallucinations.
6. The **SummaryAgent** produces an overall risk assessment from validated findings. Falls back to severity-count summary if the LLM call fails.
7. HIGH/CRITICAL findings are **enriched** with +/-10 lines of surrounding file context fetched from GitHub.
8. Review comments are **posted to GitHub** as a batch review. On failure, falls back to individual inline comments.
9. Each comment is labeled with its source agent (e.g., `[security]`, `[logic_bug]`).

---

## Sample GitHub Comment

A review comment posted by the agent:

> **[security]** **Severity:** HIGH
>
> **Issue:** Hardcoded API key found in source code
>
> **Recommendation:** Move the API key to an environment variable
>
> **Suggested change:**
> ```suggestion
> api_key = os.getenv("API_KEY")
> ```

---

## Design Notes

**Diff-scoped, not repository-scoped.** The agent evaluates changed code with surrounding context, not the whole tree. This keeps cost bounded and review latency low.

**Multi-agent over monolithic.** Splitting review concerns across specialized agents means each prompt is focused and concise, producing higher-quality findings than a single prompt covering all categories.

**Per-agent models.** Critical concerns (security, logic bugs) use a larger model for accuracy. Less critical concerns use a smaller model for speed.

**Structured findings, not prose.** The model returns discrete findings with file, line, category, and severity. Structured output can be mapped to review positions, filtered, and tracked over time.

**RAG-augmented.** Repository-specific policies stored in ChromaDB are injected into each agent's prompt, so reviews reflect your team's actual standards rather than generic best practices.

**Advisory by default.** Findings are posted as comments, not as a blocking review. A reviewer that blocks merges on probabilistic output teaches people to route around it.

---

## Licence

MIT -- see [LICENSE](LICENSE).
