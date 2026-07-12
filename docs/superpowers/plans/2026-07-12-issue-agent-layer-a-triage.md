# Issue Agent — Layer A (autonomous triage) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the existing cheap triage pipeline (prefilter → gate → classify → duplicate → priority) autonomously over every open Issue in `kibarik/po-helper` (39 now) plus a safe dry-run first pass.

**Architecture:** Reuse the existing Temporal `IssueLifecycle` workflow unchanged in shape. Add a backfill script that starts one workflow per already-open Issue (webhooks never fire for existing Issues). Add a non-interactive batch mode so vague Issues escalate instead of hanging on a signal wait. Add a PAT auth path and a `DRY_RUN` guard in the GitHub client so the first full pass mutates nothing. Seed `capabilities.md` so the classifier can tell existing functionality apart from new features.

**Tech Stack:** Python 3.12, Temporal (`temporalio==1.9.0`), Instructor + OpenAI SDK against z.ai GLM, `gh` CLI, GitHub REST via `requests`, `pytest` + `pytest-asyncio` for tests, docker-compose.

## Global Constraints

- Python version: 3.12 (matches `Dockerfile` `python:3.12-slim`).
- Pinned deps already in `worker/requirements.txt`: `temporalio==1.9.0`, `instructor==1.7.2`, `openai==1.61.0`, `pydantic==2.10.5`, `requests==2.32.3`, `pyjwt[crypto]==2.10.1`. Do not bump.
- Temporal task queue name is exactly `issue-lifecycle` (registered in `worker/worker.py`, used in `webhook/main.py`). Backfill must use the same.
- Workflow ID format is exactly `issue-<repo>-<n>` (see `webhook/main.py:workflow_id_for`). Backfill must match so webhook and backfill address the same workflow.
- Target repo for the pilot: `kibarik/po-helper`.
- Existing GitHub App auth path in `worker/github_client.py` must keep working unchanged when no PAT env var is set (needed by Layer B/prod).
- The webhook path must keep working: `IssueInput` gains a field with a default so `webhook/main.py` (which does not pass it) still constructs valid input.

## File Structure

- `shared/workflow_types.py` — add `interactive: bool` to `IssueInput`. Shared dataclass, imported by workflow, activities, webhook, backfill.
- `worker/github_client.py` — add `_auth_headers()` (PAT-or-App) + `DRY_RUN` guard on the three mutating calls. Single responsibility: GitHub REST access + auth.
- `worker/activities.py` — add one activity `post_error_label` (the error-guard side effect). Content lives with the other activities.
- `worker/workflows.py` — batch-mode VAGUE escalation + wrap the autonomous sequence in a try/except that calls `post_error_label`. Orchestration only.
- `scripts/backfill.py` — new. Enumerate open Issues via `gh`, build `IssueInput`, start one workflow each. Pure helper `build_issue_input` split out for testing.
- `workspace/capabilities.md` — new. Seed content for the classifier.
- `docker-compose.yml` — bind `./workspace:/app/workspace` (replace named volume) so the seed file is present; pass `DRY_RUN`/`GH_TOKEN` via `.env`.
- `requirements-dev.txt` — new. `pytest`, `pytest-asyncio`, `pytest-timeout`.
- `tests/conftest.py` — new. Put `worker/` and repo root on `sys.path`.
- `tests/test_*.py` — new unit/integration tests per task.
- `.env` — created from `.env.example` (secrets filled by owner).

---

## Task 0: Dev environment + test harness

**Files:**
- Create: `requirements-dev.txt`
- Create: `tests/conftest.py`
- Create: `tests/__init__.py` (empty)
- Create: `pytest.ini`

**Interfaces:**
- Produces: a runnable `pytest` that can import `workflows`, `activities`, `github_client`, `llm` (from `worker/`) and `shared.workflow_types` (from repo root).

- [ ] **Step 1: Create dev requirements**

`requirements-dev.txt`:
```
pytest==8.3.4
pytest-asyncio==0.25.2
pytest-timeout==2.3.0
```

- [ ] **Step 2: Create pytest config**

`pytest.ini`:
```ini
[pytest]
asyncio_mode = auto
timeout = 120
testpaths = tests
```

- [ ] **Step 3: Create conftest to fix import paths**

`tests/conftest.py`:
```python
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# worker/ holds workflows.py, activities.py, github_client.py, llm.py
sys.path.insert(0, str(ROOT / "worker"))
# repo root holds shared/
sys.path.insert(0, str(ROOT))
```

Create empty `tests/__init__.py`.

- [ ] **Step 4: Create a Python 3.12 venv and install deps**

Run:
```bash
python3.12 -m venv .venv
.venv/bin/pip install -r worker/requirements.txt -r requirements-dev.txt
```
Expected: installs without error (temporalio 1.9.0 ships a prebuilt wheel for macOS arm64).

- [ ] **Step 5: Verify pytest collects nothing yet, cleanly**

Run: `.venv/bin/pytest -q`
Expected: `no tests ran` (exit code 5) — harness works, imports resolve.

- [ ] **Step 6: Commit**

```bash
git add requirements-dev.txt pytest.ini tests/conftest.py tests/__init__.py
git commit -m "test: add pytest harness and dev deps"
```

---

## Task 1: `interactive` flag on `IssueInput`

**Files:**
- Modify: `shared/workflow_types.py:4-11`
- Test: `tests/test_workflow_types.py`

**Interfaces:**
- Produces: `IssueInput(..., interactive: bool = True)`. Backfill sets `interactive=False`; webhook keeps the default `True`.

- [ ] **Step 1: Write the failing test**

`tests/test_workflow_types.py`:
```python
from shared.workflow_types import IssueInput


def test_interactive_defaults_true():
    issue = IssueInput(
        repo="o/r", issue_number=1, title="t", body="b",
        author_login="u", author_type="User",
    )
    assert issue.interactive is True


def test_interactive_can_be_false():
    issue = IssueInput(
        repo="o/r", issue_number=1, title="t", body="b",
        author_login="u", author_type="User", interactive=False,
    )
    assert issue.interactive is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_workflow_types.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'interactive'`.

- [ ] **Step 3: Add the field**

In `shared/workflow_types.py`, change the `IssueInput` dataclass to:
```python
@dataclass
class IssueInput:
    repo: str
    issue_number: int
    title: str
    body: str
    author_login: str
    author_type: str  # "Bot" | "User" | ...
    interactive: bool = True  # False in batch backfill: VAGUE escalates, no wait
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_workflow_types.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add shared/workflow_types.py tests/test_workflow_types.py
git commit -m "feat: add interactive flag to IssueInput for batch mode"
```

---

## Task 2: PAT auth path in `github_client`

**Files:**
- Modify: `worker/github_client.py` (add `_auth_headers`, repoint callers)
- Test: `tests/test_github_client_auth.py`

**Interfaces:**
- Produces: `_auth_headers() -> dict`. Returns a PAT Bearer header when `GH_TOKEN` or `GITHUB_TOKEN` is set; otherwise falls back to the existing `_installation_token_headers()` (GitHub App). All REST callers use `_auth_headers()`.

- [ ] **Step 1: Write the failing test**

`tests/test_github_client_auth.py`:
```python
import importlib


def _fresh(monkeypatch, **env):
    for k in ("GH_TOKEN", "GITHUB_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import github_client
    return importlib.reload(github_client)


def test_pat_header_from_gh_token(monkeypatch):
    gc = _fresh(monkeypatch, GH_TOKEN="tok123")
    headers = gc._auth_headers()
    assert headers["Authorization"] == "Bearer tok123"
    assert headers["Accept"] == "application/vnd.github+json"


def test_pat_header_prefers_gh_token_over_github_token(monkeypatch):
    gc = _fresh(monkeypatch, GH_TOKEN="tokA", GITHUB_TOKEN="tokB")
    assert gc._auth_headers()["Authorization"] == "Bearer tokA"


def test_falls_back_to_app_when_no_pat(monkeypatch):
    gc = _fresh(monkeypatch)
    called = {}

    def fake_app_headers():
        called["app"] = True
        return {"Authorization": "Bearer app-token", "Accept": "x"}

    monkeypatch.setattr(gc, "_installation_token_headers", fake_app_headers)
    assert gc._auth_headers()["Authorization"] == "Bearer app-token"
    assert called["app"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_github_client_auth.py -v`
Expected: FAIL — `AttributeError: module 'github_client' has no attribute '_auth_headers'`.

- [ ] **Step 3: Add `_auth_headers` and repoint callers**

In `worker/github_client.py`, add after `_installation_token_headers()`:
```python
def _auth_headers() -> dict:
    """PAT path for the pilot: if GH_TOKEN/GITHUB_TOKEN is set, use it
    directly and skip the GitHub App flow. Otherwise fall back to App auth."""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    return _installation_token_headers()
```

Then replace every `_installation_token_headers()` call inside `post_comment`, `add_label`, `close_issue`, `branch_exists`, and the `GH_TOKEN` derivation in `search_candidates` with `_auth_headers()`. Concretely, in `search_candidates` change:
```python
    env = {**os.environ, "GH_TOKEN": _auth_headers()["Authorization"].split(" ")[1]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_github_client_auth.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add worker/github_client.py tests/test_github_client_auth.py
git commit -m "feat: PAT auth path in github_client, App fallback preserved"
```

---

## Task 3: `DRY_RUN` guard on mutating calls

**Files:**
- Modify: `worker/github_client.py` (`post_comment`, `add_label`, `close_issue`)
- Test: `tests/test_github_client_dryrun.py`

**Interfaces:**
- Produces: when `DRY_RUN` env is truthy, `post_comment`/`add_label`/`close_issue` log intent and return without any HTTP call. Read calls (`search_candidates`, `branch_exists`) are unaffected.

- [ ] **Step 1: Write the failing test**

`tests/test_github_client_dryrun.py`:
```python
import importlib


def _fresh(monkeypatch, dry):
    monkeypatch.setenv("GH_TOKEN", "tok")
    if dry:
        monkeypatch.setenv("DRY_RUN", "1")
    else:
        monkeypatch.delenv("DRY_RUN", raising=False)
    import github_client
    return importlib.reload(github_client)


def test_dry_run_post_comment_makes_no_http_call(monkeypatch):
    gc = _fresh(monkeypatch, dry=True)

    def boom(*a, **k):
        raise AssertionError("HTTP called under DRY_RUN")

    monkeypatch.setattr(gc.requests, "post", boom)
    monkeypatch.setattr(gc.requests, "patch", boom)
    gc.post_comment("o/r", 1, "body")
    gc.add_label("o/r", 1, "priority:P1")
    gc.close_issue("o/r", 1)


def test_non_dry_run_post_comment_calls_http(monkeypatch):
    gc = _fresh(monkeypatch, dry=False)
    calls = {}

    class Resp:
        def raise_for_status(self):
            pass

    def fake_post(url, **k):
        calls["post"] = url
        return Resp()

    monkeypatch.setattr(gc.requests, "post", fake_post)
    gc.post_comment("o/r", 1, "body")
    assert "/repos/o/r/issues/1/comments" in calls["post"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_github_client_dryrun.py -v`
Expected: FAIL — `test_dry_run_...` hits `boom` (HTTP still called; no guard yet).

- [ ] **Step 3: Add the guard**

At the top of `worker/github_client.py` (after imports) add:
```python
import logging

_log = logging.getLogger("github_client")


def _dry_run() -> bool:
    return bool(os.environ.get("DRY_RUN"))
```

Then guard each mutating function as its first statement:
```python
def post_comment(repo: str, issue_number: int, body: str) -> None:
    if _dry_run():
        _log.info("[DRY_RUN] comment %s#%s: %s", repo, issue_number, body[:200])
        return
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
    resp = requests.post(url, headers=_auth_headers(), json={"body": body}, timeout=30)
    resp.raise_for_status()


def add_label(repo: str, issue_number: int, label: str) -> None:
    if _dry_run():
        _log.info("[DRY_RUN] label %s#%s += %s", repo, issue_number, label)
        return
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/labels"
    resp = requests.post(url, headers=_auth_headers(), json={"labels": [label]}, timeout=30)
    resp.raise_for_status()


def close_issue(repo: str, issue_number: int) -> None:
    if _dry_run():
        _log.info("[DRY_RUN] close %s#%s", repo, issue_number)
        return
    url = f"https://api.github.com/repos/{repo}/issues/{issue_number}"
    resp = requests.patch(url, headers=_auth_headers(), json={"state": "closed"}, timeout=30)
    resp.raise_for_status()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_github_client_dryrun.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add worker/github_client.py tests/test_github_client_dryrun.py
git commit -m "feat: DRY_RUN guard on mutating github_client calls"
```

---

## Task 4: `post_error_label` activity

**Files:**
- Modify: `worker/activities.py` (add activity), `worker/worker.py` (register it)
- Test: `tests/test_activities_error.py`

**Interfaces:**
- Produces: `async def post_error_label(issue: IssueInput) -> None` — posts a fixed "auto-processing failed" comment and adds label `advisor:error`. Called by the workflow error-guard.

- [ ] **Step 1: Write the failing test**

`tests/test_activities_error.py`:
```python
import asyncio

import activities
from shared.workflow_types import IssueInput


def test_post_error_label_comments_and_labels(monkeypatch):
    calls = []
    monkeypatch.setattr(activities.github_client, "post_comment",
                        lambda repo, n, body: calls.append(("comment", repo, n, body)))
    monkeypatch.setattr(activities.github_client, "add_label",
                        lambda repo, n, label: calls.append(("label", repo, n, label)))

    issue = IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                       author_login="u", author_type="User")
    asyncio.run(activities.post_error_label.__wrapped__(issue))

    assert ("label", "o/r", 7, "advisor:error") in calls
    assert any(c[0] == "comment" and c[1] == "o/r" and c[2] == 7 for c in calls)
```

(`.__wrapped__` calls the plain async function under the Temporal `@activity.defn` decorator.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_activities_error.py -v`
Expected: FAIL — `AttributeError: module 'activities' has no attribute 'post_error_label'`.

- [ ] **Step 3: Add the activity**

In `worker/activities.py`, add after `escalate_to_human`:
```python
@activity.defn
async def post_error_label(issue: IssueInput) -> None:
    github_client.post_comment(
        issue.repo, issue.issue_number,
        "⚠️ Автоматическая обработка не удалась. Ожидай ручного разбора.",
    )
    github_client.add_label(issue.repo, issue.issue_number, "advisor:error")
```

In `worker/worker.py`, add `activities.post_error_label,` to the `activities=[...]` list.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_activities_error.py -v`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add worker/activities.py worker/worker.py tests/test_activities_error.py
git commit -m "feat: post_error_label activity for workflow error-guard"
```

---

## Task 5: Batch-mode VAGUE escalation + error-guard in workflow

**Files:**
- Modify: `worker/workflows.py` (`IssueLifecycle.run`)
- Test: `tests/test_workflow_batch.py`

**Interfaces:**
- Consumes: `IssueInput.interactive` (Task 1), activities `intake_gate`, `escalate_to_human`, `post_error_label` (Task 4).
- Produces: workflow that, when `interactive is False` and gate is VAGUE, escalates and returns without waiting for a signal; and that on any activity failure in the autonomous sequence posts `advisor:error` and returns.

- [ ] **Step 1: Write the failing test**

`tests/test_workflow_batch.py`:
```python
import uuid

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from workflows import IssueLifecycle
from shared.workflow_types import IssueInput, GateResult

_state = {}


@activity.defn(name="prefilter_bot_and_security")
async def stub_prefilter(issue): return None


@activity.defn(name="intake_gate")
async def stub_gate_vague(issue, thread):
    return GateResult(status="VAGUE", content="need details")


@activity.defn(name="escalate_to_human")
async def stub_escalate(issue):
    _state["escalated"] = True


@pytest.mark.timeout(30)
async def test_batch_vague_escalates_without_hanging():
    _state.clear()
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client, task_queue="tq", workflows=[IssueLifecycle],
            activities=[stub_prefilter, stub_gate_vague, stub_escalate],
        ):
            await env.client.execute_workflow(
                IssueLifecycle.run,
                IssueInput(repo="o/r", issue_number=1, title="t", body="b",
                           author_login="u", author_type="User", interactive=False),
                id=f"wf-{uuid.uuid4()}", task_queue="tq",
            )
    assert _state.get("escalated") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_workflow_batch.py -v`
Expected: FAIL — the test times out (workflow enters the clarification loop and blocks on `_wait_for_signal()` with no signal), i.e. the bug this task fixes. (First run downloads the Temporal test server binary — needs network once.)

- [ ] **Step 3: Add batch escalation before the VAGUE loop**

In `worker/workflows.py`, after the first `intake_gate` call and before `while gate.status == "VAGUE":`, insert:
```python
        # Batch/backfill mode: no human answers clarifications for 39 issues,
        # so a VAGUE issue must escalate, not park on _wait_for_signal() forever.
        if gate.status == "VAGUE" and not issue.interactive:
            await workflow.execute_activity(
                activities.escalate_to_human,
                issue,
                start_to_close_timeout=timedelta(seconds=30),
            )
            return
```

- [ ] **Step 4: Wrap the autonomous sequence in the error-guard**

Wrap the body of `run` from the prefilter call through `post_priority_comment` in a `try/except`. The `await self._wait_for_signal()` at the human-decision point and everything after stays OUTSIDE the try (those are Layer C / not in scope and should not be guarded here). Concretely, structure `run` as:
```python
    @workflow.run
    async def run(self, issue: IssueInput) -> None:
        default_retry = workflow.RetryPolicy(maximum_attempts=3)
        try:
            # ... existing prefilter -> intake_gate -> (batch escalate) ->
            #     VAGUE loop -> SPAM -> classify -> duplicate -> score ->
            #     post_priority_comment ... (unchanged bodies)
            ...
        except Exception:
            await workflow.execute_activity(
                activities.post_error_label,
                issue,
                start_to_close_timeout=timedelta(seconds=30),
            )
            return

        # --- Точка решения человека №1 (вне error-guard, Layer C) ---
        decision = await self._wait_for_signal()
        # ... unchanged research/bug/openhands tail ...
```
Keep all existing activity calls and their bodies identical; only add the outer `try:` and the `except Exception:` guard, and move the `_wait_for_signal()` tail out of the try. Note: early `return`s inside the try (bot/security, escalate, spam, existing/consultation, duplicate) still return straight out of `run` — that is correct.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_workflow_batch.py -v`
Expected: PASS (1 passed) — workflow completes, `escalated` is True.

- [ ] **Step 6: Run the whole suite**

Run: `.venv/bin/pytest -q`
Expected: all tests from Tasks 1-5 pass.

- [ ] **Step 7: Commit**

```bash
git add worker/workflows.py tests/test_workflow_batch.py
git commit -m "feat: batch VAGUE escalation and error-guard in IssueLifecycle"
```

---

## Task 6: Backfill script

**Files:**
- Create: `scripts/backfill.py`
- Create: `scripts/__init__.py` (empty)
- Test: `tests/test_backfill.py`

**Interfaces:**
- Consumes: `IssueInput` (Task 1), Temporal `Client`, task queue `issue-lifecycle`, workflow name `IssueLifecycle`, ID format `issue-<repo>-<n>`.
- Produces: `build_issue_input(repo: str, item: dict) -> IssueInput` (pure, testable) and an async `main()` that lists open Issues via `gh` and starts one workflow each, catching `WorkflowAlreadyStartedError`.

- [ ] **Step 1: Write the failing test**

`tests/test_backfill.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import backfill
from shared.workflow_types import IssueInput


def test_build_issue_input_maps_bot_author():
    item = {"number": 5, "title": "t", "body": "b",
            "author": {"login": "dependabot", "is_bot": True}}
    issue = backfill.build_issue_input("o/r", item)
    assert issue == IssueInput(
        repo="o/r", issue_number=5, title="t", body="b",
        author_login="dependabot", author_type="Bot", interactive=False,
    )


def test_build_issue_input_maps_human_author_and_null_body():
    item = {"number": 6, "title": "t", "body": None,
            "author": {"login": "alice", "is_bot": False}}
    issue = backfill.build_issue_input("o/r", item)
    assert issue.author_type == "User"
    assert issue.body == ""
    assert issue.interactive is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_backfill.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backfill'`.

- [ ] **Step 3: Write the backfill script**

`scripts/backfill.py`:
```python
"""Backfill: start one IssueLifecycle workflow per already-open Issue.

GitHub never sends webhooks for Issues that already exist, so the running
service alone never processes the current backlog. This script enumerates
open Issues via `gh` and starts workflows directly against Temporal.

Runs in non-interactive batch mode (interactive=False): a VAGUE issue
escalates instead of waiting for a human clarification that will not come.

Usage:
    python scripts/backfill.py                 # all open issues of $GITHUB_REPOSITORY
    python scripts/backfill.py --issue 83      # single issue (smoke test)
    python scripts/backfill.py --limit 5       # first N
    python scripts/backfill.py --repo owner/name
"""

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from temporalio.client import Client
from temporalio.service import RPCError  # noqa: F401  (kept for clarity)

from shared.workflow_types import IssueInput

try:
    from temporalio.client import WorkflowAlreadyStartedError
except ImportError:  # older/newer layout
    from temporalio.exceptions import WorkflowAlreadyStartedError  # type: ignore

TASK_QUEUE = "issue-lifecycle"


def build_issue_input(repo: str, item: dict) -> IssueInput:
    author = item.get("author") or {}
    return IssueInput(
        repo=repo,
        issue_number=item["number"],
        title=item["title"],
        body=item.get("body") or "",
        author_login=author.get("login", ""),
        author_type="Bot" if author.get("is_bot") else "User",
        interactive=False,
    )


def list_open_issues(repo: str, limit: int) -> list[dict]:
    cmd = ["gh", "issue", "list", "--repo", repo, "--state", "open",
           "--limit", str(limit), "--json", "number,title,body,author"]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return json.loads(out or "[]")


def workflow_id_for(repo: str, n: int) -> str:
    return f"issue-{repo}-{n}"


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--issue", type=int, default=None)
    parser.add_argument("--limit", type=int, default=200)
    args = parser.parse_args()

    if not args.repo:
        raise SystemExit("set --repo or GITHUB_REPOSITORY")

    if args.issue is not None:
        items = [i for i in list_open_issues(args.repo, 200) if i["number"] == args.issue]
        if not items:
            raise SystemExit(f"issue #{args.issue} not found among open issues")
    else:
        items = list_open_issues(args.repo, args.limit)

    client = await Client.connect(os.environ.get("TEMPORAL_ADDRESS", "localhost:7233"))

    started, skipped = 0, 0
    for item in items:
        issue = build_issue_input(args.repo, item)
        wf_id = workflow_id_for(args.repo, issue.issue_number)
        try:
            await client.start_workflow(
                "IssueLifecycle", issue, id=wf_id, task_queue=TASK_QUEUE,
            )
            started += 1
            print(f"started {wf_id}")
        except WorkflowAlreadyStartedError:
            skipped += 1
            print(f"skip {wf_id} (already running)")
    print(f"done: started={started} skipped={skipped} total={len(items)}")


if __name__ == "__main__":
    asyncio.run(main())
```

Create empty `scripts/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_backfill.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/backfill.py scripts/__init__.py tests/test_backfill.py
git commit -m "feat: backfill script starts one workflow per open issue"
```

---

## Task 7: Seed `capabilities.md`

**Files:**
- Create: `workspace/capabilities.md`

**Interfaces:**
- Produces: `workspace/capabilities.md`, read by `classify_issue` at `/app/workspace/capabilities.md` (Task 8 mounts `./workspace` there).

- [ ] **Step 1: Create the file**

`workspace/capabilities.md` — list po-helper's known functionality so the classifier can tell EXISTING from FEATURE. Source: po-helper README "Что внутри" table.
```markdown
# po-helper — известный функционал

Классификатор использует этот список, чтобы отличать существующий функционал
(EXISTING) от новых фич (FEATURE). Обновлять при добавлении навыков.

## Пайплайны и команды
- OKR — квартальное планирование: `/okr-context-gen … /okr-deliver` (8 стадий).
- Спринт — roadmap + план + материализация в JIRA + факт: `/sprint-roadmap`,
  `/sprint-sync … /sprint-deliver`, `/sprint-build`, `/sprint-activate`, `/sprint-fact`.
- БФТ — бизнес-функциональные требования по эпику: `/bft-value … /bft-deliver` (10 стадий).
- Внешние запросы — скоринг + routing: `/req-context … /req-handoff` (7 стадий).
- Задача в JIRA: `/jira-task`.
- Инфо-каналы: `/channel-map`, `/channel-list`, `/channel-route`.
- Summary встреч: `/summary`.
- Дейлики: `/daily-review`.
- Контекст: `/po-research`.
- Релизы: `/release-frame`, `/release-baseline`, `/release-sync`, `/release-gate`.
- Визуализация: `/diagram-view`.
- Карта людей: `/people-links`, `/people-map`.
- Калибровка нексуса: `/radar-graph`, `/radar-calibrate`, `/radar-review`.
- Confluence-индексатор: `/cindex <space>` (6 стадий).
- Операционный штаб: `backlog board` (MCP backlog).
- Онбординг PAF: `/paf-init`, `/paf-nexus-create` (GROUND Vault).
- Контекст-recall: `entire search`, чат-агент `entire-search`.

## Инфраструктура
- Установка/обновление: `install.sh`, `install.sh --update`.
- Доменный профиль: `.claude/domain-profile.md`.
- GROUND Vault: Кортекс → Нексус → продуктовый процесс.
```

- [ ] **Step 2: Commit**

```bash
git add workspace/capabilities.md
git commit -m "docs: seed capabilities.md from po-helper skill catalog"
```

---

## Task 8: docker-compose workspace bind + `.env`

**Files:**
- Modify: `docker-compose.yml:63-74`
- Create: `.env` (from `.env.example`, owner fills secrets)

**Interfaces:**
- Produces: `worker` container sees `workspace/capabilities.md` at `/app/workspace/capabilities.md`; `DRY_RUN`, `GH_TOKEN`, `GITHUB_REPOSITORY`, `ZAI_*` come from `.env`.

- [ ] **Step 1: Bind the workspace directory**

In `docker-compose.yml`, in the `worker` service `volumes:` block, replace the named-volume line for workspace with a bind mount:
```yaml
    volumes:
      - ./prompts:/app/prompts:ro
      - ./config:/app/config:ro
      - ./workspace:/app/workspace
```
Then remove `worker_workspace` from the top-level `volumes:` block (leave `pgdata`).

- [ ] **Step 2: Create `.env`**

Copy `.env.example` to `.env` and fill for the pilot:
```bash
cp .env.example .env
```
Set in `.env` (owner provides secret values):
```
GITHUB_REPOSITORY=kibarik/po-helper
GITHUB_WEBHOOK_SECRET=unused-in-layer-a
ZAI_API_KEY=<owner-provided>
GH_TOKEN=<fine-grained PAT: Issues r/w, Contents r on kibarik/po-helper>
DRY_RUN=1
```
Leave `GITHUB_APP_ID`/`GITHUB_INSTALLATION_ID`/`GITHUB_PRIVATE_KEY_PATH` empty — the PAT path (Task 2) makes them unnecessary for Layer A. `.env` is gitignored; confirm with `git check-ignore .env` (expected: prints `.env`). If not ignored, add `.env` to `.gitignore` and commit that.

- [ ] **Step 3: Verify compose config is valid**

Run: `docker compose config >/dev/null && echo OK`
Expected: `OK` (no YAML/interpolation errors; `.env` present).

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "chore: bind ./workspace into worker for capabilities.md"
```
(Do not commit `.env`.)

---

## Task 9: End-to-end DRY_RUN verification, then live run

This task has no unit test — it is the real end-to-end verification the spec
requires (observed behavior in Temporal UI + real Issue state), gated behind
`DRY_RUN` so the first full pass mutates nothing.

**Interfaces:**
- Consumes: everything from Tasks 1-8. `GH_TOKEN`, `ZAI_API_KEY`, `DRY_RUN=1` set in `.env`.

- [ ] **Step 1: Bring up the stack (no webhook needed in Layer A)**

Run:
```bash
docker compose up --build -d postgres temporal temporal-ui worker
docker compose logs -f worker
```
Expected in worker logs: `Worker started, listening on task queue 'issue-lifecycle'`. Open http://localhost:8080 (Temporal UI).

- [ ] **Step 2: Smoke one representative issue in DRY_RUN**

Pick a clear feature-request (e.g. #83). Run backfill from the host venv (Temporal is published on `localhost:7233`):
```bash
GITHUB_REPOSITORY=kibarik/po-helper .venv/bin/python scripts/backfill.py --issue 83
```
Expected: prints `started issue-kibarik/po-helper-83`. In Temporal UI the workflow appears and reaches `post_priority_comment`, then parks at the human-decision `_wait_for_signal()` (status Running). In `docker compose logs worker` you see `[DRY_RUN] label ... priority:PN` and `[DRY_RUN] comment ...` — and NO real comment appears on the GitHub Issue.

- [ ] **Step 3: Verify GLM/z.ai schema compatibility**

Confirm the worker logs show the gate/classify/priority activities completing (Instructor returned valid Pydantic objects) with no repeated schema-retry errors. If Instructor errors on GLM tool/schema, that is the Ф1 blocker from the spec — stop and resolve before the full run.

- [ ] **Step 4: Full DRY_RUN over all open issues**

Run:
```bash
GITHUB_REPOSITORY=kibarik/po-helper .venv/bin/python scripts/backfill.py
```
Expected: `done: started=39 skipped=0 total=39` (numbers may differ). In Temporal UI every workflow reaches parking or a terminal state (spam/duplicate/existing/escalated). Review worker logs for every intended `[DRY_RUN] close ...` — these are the auto-closes; confirm none target an Issue that should stay open.

- [ ] **Step 5: Owner review gate**

Present the DRY_RUN log summary (per issue: intended labels, priority, any intended close) to the owner. Get explicit approval before mutating real Issues. Do not proceed without it.

- [ ] **Step 6: Live run**

Set `DRY_RUN=` (empty) in `.env`, then:
```bash
docker compose up -d worker   # reload env
GITHUB_REPOSITORY=kibarik/po-helper .venv/bin/python scripts/backfill.py
```
Expected: real `priority:PN` labels + breakdown comments appear on the po-helper Issues; spam/duplicate/existing get their labels and closes. Re-running is safe (already-running workflows are skipped).

- [ ] **Step 7: Confirm the success criterion**

Verify in GitHub that every open Issue now carries a triage label (`priority:PN`, or `advisor:*`, or `duplicate`/`spam`/`needs-human-triage`/`advisor:error`). That is criterion 1 ("система прошлась по каждому") met. Criterion 2 (new issues auto-processed) is Layer B — see `docs/roadmap-post-layer-a.md`.

---

## Self-Review notes

- Spec "В объёме" items map to tasks: pipeline run → Task 9; backfill + batch mode → Tasks 5,6; PAT → Task 2; capabilities.md → Tasks 7,8; DRY_RUN → Task 3,9; docker-compose local → Tasks 8,9. Author mapping (gap 6) → Task 6. VAGUE hang (gap 5) → Task 5. Error-guard → Tasks 4,5.
- Out-of-scope (webhook/Layer B, research/bug/Layer C, calibration) correctly absent — tracked in `docs/roadmap-post-layer-a.md`.
- Type consistency: `IssueInput(..., interactive=False)` used in Tasks 5,6 matches the field added in Task 1. `build_issue_input` / `post_error_label` / `_auth_headers` / `_dry_run` names are used consistently across tasks.
