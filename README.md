
# CodeReviewAgent

An AI-powered reviewer for GitHub pull requests. It reads the diff on an open PR, evaluates it against a versioned set of review policies, and posts structured feedback as review comments — covering code quality, logic errors, best-practice violations, and opportunities to modernise.

The point is not to replace human review. It is to handle the mechanical layer — the conventions, the missed edge cases, the patterns a team has already agreed on — so reviewers spend their attention on design and correctness.

---

## Why the policy layer is separate

Most review bots hard-code their rules. That makes the rules invisible to the people they govern, and it means changing a standard requires a code change and a redeploy.

Here, review standards live in `policies/`, entirely outside the application in `app/`. This has three consequences:

- **Rules are readable by non-authors.** A tech lead or security reviewer can read `policies/` without reading Python.
- **Rules are versioned independently.** Every change to a standard is a diff with an author and a date — an audit trail of how the team's engineering standards evolved.
- **Rules change without redeploying.** Updating a policy is a config change, not a release.

In a regulated environment, this matters more than convenience: when an auditor asks "what were your code review standards in March, and who approved the change?", the answer is `git log policies/`.

---

## Architecture

```
CodeReviewAgent/
├── app/              # Application: webhook handling, diff parsing, model calls, comment posting
├── policies/         # Review standards, versioned separately from application code
├── requirements.txt
└── LICENSE           # MIT
```

Request flow:

```
GitHub PR event
      │
      ▼
  webhook  ──►  diff parser  ──►  policy loader  ──►  model evaluation
                                                            │
                                                            ▼
                                              structured findings
                                                            │
                                                            ▼
                                           review comments posted to the PR
```

The diff parser reduces a pull request to reviewable units so that only changed code — plus the context needed to judge it — is evaluated. The policy loader resolves which standards apply. The model evaluates each unit against those standards and returns structured findings, which are mapped back to file and line positions before posting.

---

## Policy format

<!-- REPLACE THIS BLOCK with a real example from your policies/ directory -->

```yaml
# policies/example.yml
id: no-force-unwrap
category: code-quality
severity: warning
applies_to:
  - "**/*.swift"
description: >
  Force unwrapping hides a crash behind a compiler pass. Prefer guard let,
  if let, or an explicit precondition with a message.
guidance: |
  Flag force unwraps outside of tests. Suggest the safe alternative that
  fits the surrounding control flow rather than a generic rewrite.
```

Each policy declares what it applies to, how serious a violation is, and what guidance the reviewer should give. Adding a standard means adding a file here — no application change.

---

## Sample output

<!-- REPLACE with a real screenshot or pasted comment from a PR the agent reviewed -->

> **`src/payments/TransactionService.swift:142`** — *warning · code-quality*
>
> Force unwrap on an optional returned from a network call. If the response
> shape changes, this crashes in production rather than failing gracefully.
> Consider `guard let` with an early return so the caller can handle the
> absent case.

---

## Getting started

```bash
git clone https://github.com/AfzalSiddiqui/CodeReviewAgent.git
cd CodeReviewAgent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Configuration:

```bash
export GITHUB_TOKEN=...        # repo scope; used to read diffs and post comments
export MODEL_API_KEY=...       # your model provider key
export WEBHOOK_SECRET=...      # validates incoming GitHub webhook payloads
```

Run it:

```bash
python -m app                  # <-- REPLACE with your actual entry point
```

Then point a GitHub webhook at `/webhook` for **Pull request** events.

---

## Design notes and trade-offs

**Diff-scoped, not repository-scoped.** The agent evaluates changed code with surrounding context, not the whole tree. This keeps cost bounded and review latency low, at the cost of missing issues that only appear across files the PR didn't touch.

**Findings are structured, not prose.** The model returns discrete findings with a file, a line, a category and a severity, rather than a paragraph of commentary. Structured output can be mapped to review positions, filtered by severity, and counted over time — free-text cannot.

**Advisory by default.** Findings are posted as comments, not as a blocking review. A reviewer that blocks merges on probabilistic output teaches people to route around it.

### What would change at scale

- **Caching** on unchanged hunks across force-pushes, to avoid re-reviewing identical code
- **Policy scoping** per directory or team, so a monorepo can carry several standards without conflict
- **Feedback signal** — tracking which findings get resolved versus dismissed, to tune policies against real reviewer behaviour
- **Batching** related findings into a single review rather than separate comments, to reduce PR noise

---

## Licence

MIT — see [LICENSE](LICENSE).
