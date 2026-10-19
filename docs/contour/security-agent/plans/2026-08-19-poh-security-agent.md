# poh-security-agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `poh-security-agent` — a standalone git repo distributing an autonomous, harness-embeddable Semgrep-based security-audit toolkit (Claude Code skills + harness-agnostic docs + GitHub Actions workflows + a demo custom-rules bundle that installers are required to personalize).

**Architecture:** Static file bundle, no runtime service. Two skill files (`security-audit`, `security-setup`) drive an agent to run Semgrep locally and to install/personalize the bundle in a target repo. Two GitHub Actions workflow templates get copied into a target repo's `.github/workflows/`. A demo `config/semgrep/` rule set (ported verbatim from the provided `semgrep.zip`) ships as the starting template, validated by its own `run_tests.sh` and by a CI workflow in this repo.

**Tech Stack:** Semgrep CLI (rules are YAML), GitHub Actions (YAML), Bash (`run_tests.sh`), Markdown (SKILL.md / AGENTS.md / README.md — this repo has no application code).

## Global Constraints

- Custom rules bundle from `semgrep.zip` is ported as a **demo/template**, not tailored guidance — README must lead with a personalization warning before any Quick Start content.
- `/security-setup` never writes `SEMGREP_APP_TOKEN` itself and never touches GitHub Secrets — token setup stays a manual, documented step.
- `/security-audit` must degrade gracefully without `SEMGREP_APP_TOKEN` (community `p/*` packs still work; Pro features explicitly called out as unavailable) rather than fail silently.
- `/security-setup` only detects tech stack (language/framework) to select rule folders — it must not attempt to infer target-project business logic.
- No auto-fix of findings without explicit user request, in either skill.
- License: MIT. Target GitHub org: `po-helper-org`. Repo: `poh-security-agent`, public.
- Out of scope for this plan (do not build): SCA/dependency-audit skill, standalone secrets-scanner skill.

---

### Task 1: Repo skeleton, LICENSE, gitignore

**Files:**
- Create: `LICENSE`
- Create: `.gitignore`
- Create: `config/semgrep/.gitkeep` (removed once Task 2 populates the dir — see Task 2)
- Create: `skills/.gitkeep` (removed once Task 5 populates the dir)
- Create: `workflows/.gitkeep` (removed once Task 3 populates the dir)
- Create: `examples/.gitkeep` (removed once Task 9 populates the dir)

**Interfaces:**
- Consumes: nothing (first task)
- Produces: directory skeleton `config/semgrep/`, `skills/`, `workflows/`, `examples/` that later tasks populate; `LICENSE` referenced by README (Task 8)

- [ ] **Step 1: Create directory skeleton with placeholders**

```bash
cd ~/projects/poh-org/poh-security-agent
mkdir -p config/semgrep skills workflows examples
touch config/semgrep/.gitkeep skills/.gitkeep workflows/.gitkeep examples/.gitkeep
```

- [ ] **Step 2: Add .gitignore**

```
# .gitignore
*.log
.DS_Store
semgrep-results.sarif
pr-results.json
/tmp/
```

Write this content to `.gitignore`.

- [ ] **Step 3: Add MIT LICENSE**

Write to `LICENSE` (replace `<YEAR>`/`<HOLDER>` with `2026` / `po-helper-org`):

```
MIT License

Copyright (c) 2026 po-helper-org

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 4: Verify skeleton**

Run: `find ~/projects/poh-org/poh-security-agent -maxdepth 2 -type d | sort`
Expected output includes: `config/semgrep`, `examples`, `skills`, `workflows` (plus `.git`, `docs`)

- [ ] **Step 5: Commit**

```bash
cd ~/projects/poh-org/poh-security-agent
git add LICENSE .gitignore config/semgrep/.gitkeep skills/.gitkeep workflows/.gitkeep examples/.gitkeep
git commit -m "chore: repo skeleton, MIT license, gitignore"
```

---

### Task 2: Port demo Semgrep custom rules from semgrep.zip

**Files:**
- Create: `config/semgrep/README.md`
- Create: `config/semgrep/base/temporal-determinism.yaml`
- Create: `config/semgrep/base/tests/workflows/test_temporal_violations.py`
- Create: `config/semgrep/python/pydantic-io.yaml`
- Create: `config/semgrep/python/async-patterns.yaml`
- Create: `config/semgrep/python/tests/workflows/test_pydantic_io.py`
- Create: `config/semgrep/python/tests/activities/test_pydantic_io.py`
- Create: `config/semgrep/python/tests/async-patterns.py`
- Create: `config/semgrep/typescript/react-patterns.yaml`
- Create: `config/semgrep/typescript/tests/react-patterns.tsx`
- Create: `config/semgrep/python-security.yaml`
- Create: `config/semgrep/python-best-practices.yaml`
- Create: `config/semgrep/typescript-security.yaml`
- Create: `config/semgrep/ai-hygiene.yaml`
- Create: `config/semgrep/tests/run_tests.sh`
- Create: `config/semgrep/tests/ai-hygiene.py`
- Delete: `config/semgrep/.gitkeep`

**Interfaces:**
- Consumes: extracted source at `/tmp/semgrep_inspect/semgrep/` (from `~/Downloads/semgrep.zip`)
- Produces: `config/semgrep/` demo rule tree that Task 4's CI workflow validates, that `skills/security-audit` (Task 5) points `semgrep scan --config` at, and that `skills/security-setup` (Task 6) selectively copies from into target repos

- [ ] **Step 1: Copy rule files and tests verbatim from the extracted zip**

```bash
cd ~/projects/poh-org/poh-security-agent
rm -f config/semgrep/.gitkeep
SRC=/tmp/semgrep_inspect/semgrep
cp "$SRC/README.md" config/semgrep/README.md
cp "$SRC/ai-hygiene.yaml" config/semgrep/ai-hygiene.yaml
cp "$SRC/python-best-practices.yaml" config/semgrep/python-best-practices.yaml
cp "$SRC/python-security.yaml" config/semgrep/python-security.yaml
cp "$SRC/typescript-security.yaml" config/semgrep/typescript-security.yaml

mkdir -p config/semgrep/base/tests/workflows
cp "$SRC/base/temporal-determinism.yaml" config/semgrep/base/temporal-determinism.yaml
cp "$SRC/base/tests/workflows/test_temporal_violations.py" config/semgrep/base/tests/workflows/test_temporal_violations.py

mkdir -p config/semgrep/python/tests/workflows config/semgrep/python/tests/activities
cp "$SRC/python/pydantic-io.yaml" config/semgrep/python/pydantic-io.yaml
cp "$SRC/python/async-patterns.yaml" config/semgrep/python/async-patterns.yaml
cp "$SRC/python/tests/workflows/test_pydantic_io.py" config/semgrep/python/tests/workflows/test_pydantic_io.py
cp "$SRC/python/tests/activities/test_pydantic_io.py" config/semgrep/python/tests/activities/test_pydantic_io.py
cp "$SRC/python/tests/async-patterns.py" config/semgrep/python/tests/async-patterns.py

mkdir -p config/semgrep/typescript/tests
cp "$SRC/typescript/react-patterns.yaml" config/semgrep/typescript/react-patterns.yaml
cp "$SRC/typescript/tests/react-patterns.tsx" config/semgrep/typescript/tests/react-patterns.tsx

mkdir -p config/semgrep/tests
cp "$SRC/tests/run_tests.sh" config/semgrep/tests/run_tests.sh
chmod +x config/semgrep/tests/run_tests.sh
cp "$SRC/tests/ai-hygiene.py" config/semgrep/tests/ai-hygiene.py
```

- [ ] **Step 2: Add a demo-bundle notice to the top of `config/semgrep/README.md`**

Prepend this block (before the existing `# Semgrep Custom Rules` heading) to `config/semgrep/README.md`:

```markdown
> ⚠️ **This is a demo rule bundle**, originally written for a Temporal/Pydantic
> AI B2B Sales Platform. It is a *starting template*, not tailored guidance for
> your project. Run `/security-setup` (see `skills/security-setup/SKILL.md`) or
> personalize this directory by hand before relying on scan results. See the
> repo root [README.md](../../README.md) for the full requirement.

---

```

- [ ] **Step 3: Validate every rule file's syntax**

Run: `cd ~/projects/poh-org/poh-security-agent && find config/semgrep -name "*.yaml" -type f -exec semgrep --validate --config {} \;`
Expected: each line ends with `Config is valid` (or equivalent semgrep 1.161.0 success message), no `invalid configuration file` errors.

- [ ] **Step 4: Run the bundled rule test suite**

Run: `cd ~/projects/poh-org/poh-security-agent && bash config/semgrep/tests/run_tests.sh`
Expected: final line `All tests passed!` and exit code `0`. If any suite fails, fix the copied file to match its original from `/tmp/semgrep_inspect/semgrep/` byte-for-byte (do not edit rule logic in this task — only the README notice from Step 2 is an intentional change) and re-run.

- [ ] **Step 5: Commit**

```bash
cd ~/projects/poh-org/poh-security-agent
git add config/semgrep
git commit -m "feat: port demo Semgrep custom rules bundle from semgrep.zip"
```

---

### Task 3: Port GitHub Actions workflow templates

**Files:**
- Create: `workflows/semgrep-full.yml`
- Create: `workflows/semgrep-pr.yml`
- Delete: `workflows/.gitkeep`

**Interfaces:**
- Consumes: `~/Downloads/semgrep.yml`, `~/Downloads/semgrep-pr.yml` (source workflows, used verbatim except the `SEMGREP_RULES` block)
- Produces: `workflows/semgrep-full.yml`, `workflows/semgrep-pr.yml` — copied into a target repo's `.github/workflows/` by `skills/security-setup` (Task 6), which then rewrites their `SEMGREP_RULES` block

- [ ] **Step 1: Copy both workflow files verbatim**

```bash
cd ~/projects/poh-org/poh-security-agent
rm -f workflows/.gitkeep
cp ~/Downloads/semgrep.yml workflows/semgrep-full.yml
cp ~/Downloads/semgrep-pr.yml workflows/semgrep-pr.yml
```

- [ ] **Step 2: Replace the hardcoded `SEMGREP_RULES` block in both files with a personalization placeholder**

In `workflows/semgrep-full.yml`, find:

```yaml
        env:
          SEMGREP_APP_TOKEN: ${{ secrets.SEMGREP_APP_TOKEN }}
          SEMGREP_RULES: |
            p/default
            p/owasp-top-ten
            p/cwe-top-25
            p/python
            p/flask
            p/fastapi
            p/jwt
            p/secrets
            p/sql-injection
            p/command-injection
            p/typescript
            p/react
            p/nextjs
            p/nodejs
            config/semgrep/
```

Replace with:

```yaml
        env:
          SEMGREP_APP_TOKEN: ${{ secrets.SEMGREP_APP_TOKEN }}
          # TODO: personalize via `/security-setup` or by hand — see README.md
          # "Before you start" section. This is a demo rule selection.
          SEMGREP_RULES: |
            p/default
            p/owasp-top-ten
            p/cwe-top-25
            p/python
            p/flask
            p/fastapi
            p/jwt
            p/secrets
            p/sql-injection
            p/command-injection
            p/typescript
            p/react
            p/nextjs
            p/nodejs
            config/semgrep/
```

Apply the identical replacement (same before/after block) in `workflows/semgrep-pr.yml`.

- [ ] **Step 3: Rename job-level names to make the source repo identifiable in Actions UI**

In `workflows/semgrep-full.yml`, confirm `name: Semgrep Security Scan` at the top (leave as-is — target repos will see this name in their own Actions tab, which is fine since `/security-setup` copies the file directly).

No edit needed if it already reads `name: Semgrep Security Scan` — verify with:

Run: `head -1 workflows/semgrep-full.yml`
Expected: `name: Semgrep Security Scan`

Run: `head -1 workflows/semgrep-pr.yml`
Expected: `name: Semgrep PR Check (Fast)`

- [ ] **Step 4: Lint both workflow files**

Run: `actionlint workflows/semgrep-full.yml workflows/semgrep-pr.yml`
Expected: no output (exit code 0). If actionlint reports issues unrelated to the `SEMGREP_RULES` edit (i.e., pre-existing in the source files), fix them by editing the flagged line directly.

- [ ] **Step 5: Commit**

```bash
cd ~/projects/poh-org/poh-security-agent
git add workflows/semgrep-full.yml workflows/semgrep-pr.yml
git commit -m "feat: add semgrep-full and semgrep-pr workflow templates"
```

---

### Task 4: CI for this repo — validate the demo rule bundle on every push

**Files:**
- Create: `.github/workflows/test-rules.yml`

**Interfaces:**
- Consumes: `config/semgrep/tests/run_tests.sh` (Task 2)
- Produces: CI gate for this repo (not copied into target repos — target repos get `workflows/semgrep-full.yml` / `workflows/semgrep-pr.yml` instead)

- [ ] **Step 1: Write the CI workflow**

Create `.github/workflows/test-rules.yml`:

```yaml
name: Test demo rule bundle

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_dispatch:

jobs:
  test-rules:
    name: Validate and test config/semgrep/
    runs-on: ubuntu-22.04
    container:
      image: returntocorp/semgrep:latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Run rule test suite
        run: bash config/semgrep/tests/run_tests.sh
```

- [ ] **Step 2: Lint the workflow**

Run: `actionlint .github/workflows/test-rules.yml`
Expected: no output (exit code 0)

- [ ] **Step 3: Commit**

```bash
cd ~/projects/poh-org/poh-security-agent
git add .github/workflows/test-rules.yml
git commit -m "ci: validate demo semgrep rule bundle on push"
```

---

### Task 5: `skills/security-audit/SKILL.md`

**Files:**
- Create: `skills/security-audit/SKILL.md`
- Delete: `skills/.gitkeep` (only if Task 6 hasn't already removed it — check before deleting)

**Interfaces:**
- Consumes: `config/semgrep/` (Task 2) as the fallback demo config path; target repo's own `config/semgrep/` if `/security-setup` (Task 6) has already run
- Produces: `/security-audit` slash-command skill, documented in `README.md` (Task 8) and `AGENTS.md` (Task 7)

- [ ] **Step 1: Write the skill file**

Create `skills/security-audit/SKILL.md`:

```markdown
---
name: security-audit
description: Run a local Semgrep security scan before committing — surfaces file:line findings grouped by severity so they can be fixed before the CI gate catches them. Trigger on "/security-audit", "проверь код на уязвимости", "security scan", "audit this before I commit".
---

# security-audit

Run this before committing to catch what the CI Semgrep gate (`.github/workflows/semgrep-pr.yml`, `.github/workflows/semgrep-full.yml` once `/security-setup` has installed them) would catch — but locally, without waiting for a CI round trip.

## Steps

1. **Locate the rule config.**
   - Check for `config/semgrep/` in the current repository root.
   - If it exists, use it: `CONFIG_PATH=config/semgrep/`.
   - If it does **not** exist, the target repo has not run `/security-setup` yet. Tell the user: "No `config/semgrep/` found in this repo — falling back to the poh-security-agent demo bundle. Run `/security-setup` first to get a config tailored to this project." Then use the demo bundle shipped in this skill's own repo (the `config/semgrep/` directory next to this `SKILL.md`'s repo root) as `CONFIG_PATH`.

2. **Check for `SEMGREP_APP_TOKEN`.**
   - Run `echo $SEMGREP_APP_TOKEN | wc -c` (or check the environment directly).
   - If unset: proceed anyway — Semgrep's community `p/*` registry packs (`p/default`, `p/owasp-top-ten`, etc.) and everything under `config/semgrep/` work without a token. Tell the user up front: "No SEMGREP_APP_TOKEN set — running with community rule packs only. Semgrep Pro features (AppSec agent, full managed review) are unavailable until a token is configured; see README.md."
   - If set: proceed normally, no message needed.

3. **Run the scan.**

   ```bash
   semgrep scan --config "$CONFIG_PATH" --severity ERROR --severity WARNING --json --output /tmp/security-audit-results.json
   ```

   - If this command fails (non-zero exit AND no JSON output — Semgrep exits non-zero on findings too, that's expected and not a failure), do not report "no issues found." Instead:
     - Run `semgrep --validate --config "$CONFIG_PATH"` to get the specific YAML/config error.
     - Report the exact validation error to the user and stop. Do not guess at a fix without seeing the error.

4. **Parse and report findings.**
   - Read `/tmp/security-audit-results.json`, extract the `.results` array.
   - Group by `.extra.severity` (`ERROR` first, then `WARNING`).
   - For each finding print: `<path>:<start.line> — <extra.message>` (rule id: `<check_id>`).
   - If `.results` is empty: report "No findings at ERROR/WARNING severity."

5. **Offer next steps — do not auto-fix.**
   - List the findings as candidates for a fix.
   - Ask the user which ones (if any) to fix now. Only edit code the user explicitly asks to be fixed.

## Notes

- This skill never modifies `.github/workflows/` or `config/semgrep/` — that's `/security-setup`'s job.
- This skill never reads or writes `SEMGREP_APP_TOKEN` — it only checks whether it's set.
```

- [ ] **Step 2: Verify frontmatter parses as YAML**

Run: `python3 -c "import yaml,sys; f=open('skills/security-audit/SKILL.md').read(); fm=f.split('---')[1]; yaml.safe_load(fm); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd ~/projects/poh-org/poh-security-agent
rm -f skills/.gitkeep
git add skills/security-audit/SKILL.md
git rm --cached skills/.gitkeep 2>/dev/null || true
git commit -m "feat: add /security-audit skill"
```

---

### Task 6: `skills/security-setup/SKILL.md`

**Files:**
- Create: `skills/security-setup/SKILL.md`

**Interfaces:**
- Consumes: `config/semgrep/base/`, `config/semgrep/python/`, `config/semgrep/typescript/` (Task 2), `workflows/semgrep-full.yml`, `workflows/semgrep-pr.yml` (Task 3)
- Produces: `/security-setup` slash-command skill, documented in `README.md` (Task 8) and `AGENTS.md` (Task 7); this is what installs `config/semgrep/` and `.github/workflows/*.yml` into a *target* repo, which `/security-audit` (Task 5) then relies on being present

- [ ] **Step 1: Write the skill file**

Create `skills/security-setup/SKILL.md`:

```markdown
---
name: security-setup
description: One-time install of the poh-security-agent Semgrep toolkit into a target repository — detects the tech stack, copies the relevant demo rule folders and GitHub Actions workflows, and prints a personalization checklist. Trigger on "/security-setup", "install security agent", "set up semgrep for this repo".
---

# security-setup

Run once, in the repository this toolkit is being installed into (not in `poh-security-agent` itself, unless that's the repo being set up).

**This installs a demo/template config.** It does not write project-specific rules — it only chooses which pre-existing rule folders and registry packs are relevant to the detected stack. The user must still review and adapt `config/semgrep/` afterward. Say this explicitly at the end of the run (Step 6).

## Steps

1. **Detect the target repo's tech stack.**
   - Python: `package.json` absent AND (`pyproject.toml` present OR `requirements.txt` present OR any `*.py` file exists at depth <= 3).
   - TypeScript/JS: `package.json` present, OR any `*.ts`/`*.tsx`/`*.js`/`*.jsx` file exists at depth <= 3.
   - Both can be true (polyglot repo) — that's fine, install both.
   - If neither is detected, tell the user and ask which stack to target instead of guessing.

2. **Copy the base rules (always).**

   ```bash
   mkdir -p config/semgrep/base
   cp -r <poh-security-agent-repo>/config/semgrep/base/. config/semgrep/base/
   cp <poh-security-agent-repo>/config/semgrep/README.md config/semgrep/README.md
   mkdir -p config/semgrep/tests
   cp <poh-security-agent-repo>/config/semgrep/tests/run_tests.sh config/semgrep/tests/run_tests.sh
   chmod +x config/semgrep/tests/run_tests.sh
   ```

   (`<poh-security-agent-repo>` is wherever this toolkit was installed from — a local clone path or a submodule path. Ask the user if it isn't obvious from context.)

3. **Copy stack-specific rule folders only for detected stacks.**

   - If Python detected:
     ```bash
     mkdir -p config/semgrep/python
     cp -r <poh-security-agent-repo>/config/semgrep/python/. config/semgrep/python/
     cp <poh-security-agent-repo>/config/semgrep/python-security.yaml config/semgrep/python-security.yaml
     cp <poh-security-agent-repo>/config/semgrep/python-best-practices.yaml config/semgrep/python-best-practices.yaml
     ```
   - If TypeScript/JS detected:
     ```bash
     mkdir -p config/semgrep/typescript
     cp -r <poh-security-agent-repo>/config/semgrep/typescript/. config/semgrep/typescript/
     cp <poh-security-agent-repo>/config/semgrep/typescript-security.yaml config/semgrep/typescript-security.yaml
     ```
   - Do **not** copy the folder for a stack that wasn't detected.

4. **Copy and personalize the workflow templates.**

   ```bash
   mkdir -p .github/workflows
   cp <poh-security-agent-repo>/workflows/semgrep-full.yml .github/workflows/semgrep-full.yml
   cp <poh-security-agent-repo>/workflows/semgrep-pr.yml .github/workflows/semgrep-pr.yml
   ```

   Edit the `SEMGREP_RULES` block in both copied files: remove any pack not relevant to the detected stack. Reference list:
   - Python detected → keep `p/python`, `p/flask`, `p/fastapi`, `p/jwt`, `p/sql-injection`, `p/command-injection`
   - Python not detected → remove `p/python`, `p/flask`, `p/fastapi`
   - TypeScript/JS detected → keep `p/typescript`, `p/react`, `p/nextjs`, `p/nodejs`
   - TypeScript/JS not detected → remove `p/typescript`, `p/react`, `p/nextjs`, `p/nodejs`
   - Always keep: `p/default`, `p/owasp-top-ten`, `p/cwe-top-25`, `p/secrets`, `config/semgrep/`
   - Also remove the `# TODO: personalize via /security-setup...` comment above `SEMGREP_RULES` now that setup has run.

5. **Run the rule test suite to confirm nothing broke in the copy.**

   ```bash
   bash config/semgrep/tests/run_tests.sh
   ```

   If this fails, report the exact failure — do not silently continue.

6. **Print the personalization checklist. Always show this, verbatim structure:**

   ```
   Semgrep toolkit installed. Before you rely on it:

   [ ] Review config/semgrep/base/temporal-determinism.yaml — DELETE it if this
       project doesn't use Temporal workflows. It will false-positive otherwise.
   [ ] Review every copied *.yaml under config/semgrep/ for relevance to this
       project's actual invariants — this is a demo bundle, not your rules.
   [ ] Add project-specific rules for your own architectural constraints.
   [ ] Add SEMGREP_APP_TOKEN to GitHub repo Settings → Secrets → Actions if you
       want Semgrep Pro features (this skill will NOT do this for you).
   [ ] Run `config/semgrep/tests/run_tests.sh` again after any rule edits.
   [ ] Commit .github/workflows/semgrep-full.yml, .github/workflows/semgrep-pr.yml,
       and config/semgrep/.
   ```

## Notes

- Never writes to GitHub Secrets, never touches `SEMGREP_APP_TOKEN` beyond mentioning it.
- Never invents project-specific rule logic — only selects which pre-written folders/packs apply to the detected stack.
```

- [ ] **Step 2: Verify frontmatter parses as YAML**

Run: `python3 -c "import yaml,sys; f=open('skills/security-setup/SKILL.md').read(); fm=f.split('---')[1]; yaml.safe_load(fm); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd ~/projects/poh-org/poh-security-agent
git add skills/security-setup/SKILL.md
git commit -m "feat: add /security-setup skill"
```

---

### Task 7: `AGENTS.md` — harness-agnostic entry point

**Files:**
- Create: `AGENTS.md`

**Interfaces:**
- Consumes: content/behavior described in `skills/security-audit/SKILL.md` (Task 5), `skills/security-setup/SKILL.md` (Task 6)
- Produces: portable instructions usable by any agent harness that reads an `AGENTS.md`/system-prompt style file instead of Claude Code's `SKILL.md` format

- [ ] **Step 1: Write `AGENTS.md`**

Create `AGENTS.md`:

```markdown
# poh-security-agent — agent instructions

This file is the harness-agnostic entry point for agents that don't use Claude Code's `SKILL.md` / slash-command format (e.g. Cursor, Codex, or a plain system prompt). If your harness supports Claude Code skills directly, use `skills/security-audit/SKILL.md` and `skills/security-setup/SKILL.md` instead — this file restates the same two capabilities in plain instruction form.

⚠️ **Before using this toolkit in a real project, read the "Before you start" section of `README.md`.** The bundled `config/semgrep/` rules are a demo set, not tailored to your project.

## Capability 1: Security audit (equivalent to `/security-audit`)

When the user asks you to check code for vulnerabilities before committing, or run a security scan:

1. Look for `config/semgrep/` in the current repo root. If absent, tell the user to run setup (Capability 2) first, and fall back to this toolkit's own `config/semgrep/` demo bundle.
2. Check whether `SEMGREP_APP_TOKEN` is set. If not, tell the user you're running with community rule packs only (Pro features unavailable) and continue anyway — don't block on it.
3. Run: `semgrep scan --config <config_path> --severity ERROR --severity WARNING --json --output /tmp/security-audit-results.json`
4. If it produces no JSON (a real failure, not just findings), run `semgrep --validate --config <config_path>` and report the exact error — never claim "no issues" on a failed run.
5. Parse the JSON `.results[]`, print `path:line — message` grouped by severity (ERROR first).
6. List findings as fix candidates. Only edit code the user explicitly asks you to fix.

Full step-by-step detail: `skills/security-audit/SKILL.md`.

## Capability 2: Install and personalize (equivalent to `/security-setup`)

When the user asks you to install this toolkit into their repository:

1. Detect stack: Python (`pyproject.toml`/`requirements.txt`/`*.py` present, no `package.json`), TypeScript/JS (`package.json` or `*.ts`/`*.tsx`/`*.js`/`*.jsx` present). Ask if ambiguous — don't guess silently.
2. Always copy `config/semgrep/base/`, `config/semgrep/README.md`, `config/semgrep/tests/run_tests.sh`.
3. Copy `config/semgrep/python/` + top-level `python-*.yaml` only if Python was detected. Copy `config/semgrep/typescript/` + `typescript-security.yaml` only if TS/JS was detected.
4. Copy `workflows/semgrep-full.yml` and `workflows/semgrep-pr.yml` into `.github/workflows/`, then edit their `SEMGREP_RULES` block to drop packs for stacks that weren't detected (see `skills/security-setup/SKILL.md` step 4 for the exact keep/remove list).
5. Run `config/semgrep/tests/run_tests.sh` — report failure verbatim if it doesn't pass.
6. Print the personalization checklist from `skills/security-setup/SKILL.md` step 6, verbatim.
7. Never touch GitHub Secrets or write `SEMGREP_APP_TOKEN` — only mention where the user should add it.

Full step-by-step detail: `skills/security-setup/SKILL.md`.

## Hard rules for any harness

- Never auto-fix findings without the user explicitly asking.
- Never invent project-specific Semgrep rules on the user's behalf during setup — only select among pre-written folders based on detected stack.
- Never write `SEMGREP_APP_TOKEN` or touch GitHub Secrets.
```

- [ ] **Step 2: Commit**

```bash
cd ~/projects/poh-org/poh-security-agent
git add AGENTS.md
git commit -m "docs: add harness-agnostic AGENTS.md"
```

---

### Task 8: `README.md` with mandatory personalization warning

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: `skills/security-audit/SKILL.md`, `skills/security-setup/SKILL.md` (Tasks 5–6), `workflows/*.yml` (Task 3), `AGENTS.md` (Task 7), `LICENSE` (Task 1)
- Produces: repo root documentation — the first thing anyone (human or agent) reads

- [ ] **Step 1: Write `README.md`**

Create `README.md`:

```markdown
# poh-security-agent

Autonomous Semgrep-based security-audit toolkit, built to be embedded into an AI coding agent's harness. Two capabilities: a local pre-commit audit (`/security-audit`) and a one-time installer that personalizes this toolkit for a target repo (`/security-setup`).

---

## ⚠️ Before you start

**Personalize your Semgrep config to your repository's own needs and rules before relying on scan results.**

The rules under `config/semgrep/` are a **demo bundle** — they were originally written for a specific Temporal/Pydantic AI B2B Sales Platform project (see `config/semgrep/base/temporal-determinism.yaml` for an example that will false-positive on any project not using Temporal). Run `/security-setup` (or personalize the directory by hand) before you commit based on what this toolkit reports. Un-personalized, this is a demo setting, not an audit of your project's actual invariants.

---

## Quick start

1. **Install into your repo.** In an agent harness, run `/security-setup` from your target repository (see `skills/security-setup/SKILL.md`, or `AGENTS.md` if your harness doesn't use Claude Code skills). This copies:
   - `.github/workflows/semgrep-full.yml` — push/PR/weekly-schedule scan, uploads SARIF to GitHub Security tab
   - `.github/workflows/semgrep-pr.yml` — fast PR-diff scan, comments findings directly on the PR
   - `config/semgrep/` — the demo rule bundle, filtered to your detected stack
2. **Personalize.** Follow the checklist `/security-setup` prints — review every copied rule file, delete what doesn't apply (e.g. Temporal rules on a non-Temporal project), add your own.
3. **(Optional) Add a Semgrep token.** Add `SEMGREP_APP_TOKEN` under your repo's Settings → Secrets and variables → Actions if you want access to Semgrep's registry rule packs beyond the free tier, or Semgrep Pro (see below). Without a token, community `p/*` packs and `config/semgrep/` still run.
4. **Run a local audit before committing.** `/security-audit` (see `skills/security-audit/SKILL.md`) runs the same rule set locally and reports `file:line` findings before you push — catch what the PR check would catch, without the CI round trip.

## What you get

- **Pre-commit visibility.** See vulnerabilities before you commit, and have your AI agent fix them in place.
- **PR-level safety net.** If something slips through, `semgrep-pr.yml` comments directly on the pull request with what was missed and where.
- **Full-repo coverage on a schedule.** `semgrep-full.yml` runs on push to `master`/`develop` and weekly, uploading SARIF results to GitHub's Security tab.

If your budget allows it, consider **Semgrep Pro** — it ships an AppSec agent and automated review out of the box, on top of everything here.

## Repository layout

```
poh-security-agent/
├── README.md                 # you are here
├── AGENTS.md                 # harness-agnostic instructions (non-Claude-Code agents)
├── LICENSE                   # MIT
├── skills/
│   ├── security-audit/       # /security-audit — local pre-commit scan
│   └── security-setup/       # /security-setup — one-time install + personalization
├── workflows/                # GitHub Actions templates, copied by /security-setup
│   ├── semgrep-full.yml
│   └── semgrep-pr.yml
├── config/semgrep/           # demo rule bundle — PERSONALIZE BEFORE RELYING ON IT
│   ├── base/                 # cross-language architectural rules
│   ├── python/
│   ├── typescript/
│   └── tests/                # run_tests.sh validates + tests the bundle
└── examples/
    └── personalized-config-example.md
```

## Writing your own rules

1. Add a rule file under the relevant `config/semgrep/<language>/` directory (or `base/` if language-agnostic).
2. Add a test file alongside it with `ruleid:` / `ok:` annotations (see existing files for the pattern Semgrep's `--test` expects).
3. Validate: `semgrep --validate --config path/to/your-rule.yaml`
4. Test: `bash config/semgrep/tests/run_tests.sh`
5. Document it in `config/semgrep/README.md`.

See `examples/personalized-config-example.md` for a worked example of adapting the bundle to a different stack.

## License

MIT — see `LICENSE`.
```

- [ ] **Step 2: Verify all internal links point to files that exist**

Run:
```bash
cd ~/projects/poh-org/poh-security-agent
for f in AGENTS.md LICENSE skills/security-audit/SKILL.md skills/security-setup/SKILL.md workflows/semgrep-full.yml workflows/semgrep-pr.yml config/semgrep/base/temporal-determinism.yaml config/semgrep/README.md examples/personalized-config-example.md; do
  [ -f "$f" ] && echo "OK $f" || echo "MISSING $f"
done
```
Expected: every line reads `OK ...`. (`examples/personalized-config-example.md` is created in Task 9 — if this task runs before Task 9, expect `MISSING examples/personalized-config-example.md` and re-run this check after Task 9 instead of treating it as a blocker now.)

- [ ] **Step 3: Commit**

```bash
cd ~/projects/poh-org/poh-security-agent
git add README.md
git commit -m "docs: add README with mandatory personalization warning"
```

---

### Task 9: `examples/personalized-config-example.md`

**Files:**
- Create: `examples/personalized-config-example.md`
- Delete: `examples/.gitkeep`

**Interfaces:**
- Consumes: `config/semgrep/` structure (Task 2), `/security-setup` behavior (Task 6)
- Produces: worked example referenced by `README.md` (Task 8, "Writing your own rules" section)

- [ ] **Step 1: Write the example**

Create `examples/personalized-config-example.md`:

```markdown
# Example: personalizing the demo bundle for a different stack

Say `/security-setup` was run on a plain Go + Next.js repo (no Python, no Temporal). Here's what a correctly personalized `config/semgrep/` and workflow should look like afterward.

## What `/security-setup` would install

- `config/semgrep/base/` — copied (always copied regardless of stack)
- `config/semgrep/typescript/` — copied (Next.js detected)
- `config/semgrep/typescript-security.yaml` — copied
- `config/semgrep/python/`, `config/semgrep/python-*.yaml` — **not copied** (no Python detected)

## What you still need to do by hand

1. **Delete or rewrite `config/semgrep/base/temporal-determinism.yaml`.** This repo doesn't use Temporal — every rule in that file targets `@workflow.defn`-style decorators that don't exist here. Left in place, it does nothing (no false positives, since the pattern won't match), but it's dead weight. Delete it:
   ```bash
   rm -rf config/semgrep/base
   ```

2. **Add a Go rule folder.** The demo bundle ships no Go rules at all. Create `config/semgrep/go/` and add your own, e.g. a rule flagging unchecked `error` returns:
   ```yaml
   # config/semgrep/go/unchecked-error.yaml
   rules:
     - id: unchecked-error-return
       languages: [go]
       severity: WARNING
       message: "Error return value is not checked"
       patterns:
         - pattern: $FUNC(...)
         - pattern-not: $ERR = $FUNC(...)
         - pattern-not: $VAL, $ERR = $FUNC(...)
   ```
   Add a matching test file under `config/semgrep/go/tests/` with `ruleid:`/`ok:` cases, then:
   ```bash
   semgrep --validate --config config/semgrep/go/unchecked-error.yaml
   ```

3. **Trim `.github/workflows/semgrep-full.yml`'s `SEMGREP_RULES`.** Remove `p/python`, `p/flask`, `p/fastapi` (no Python). Add `p/golang` (Go detected, not auto-added by `/security-setup` since Go stack-detection isn't built into this toolkit yet — add it by hand).

4. **Re-run the test suite** after any of the above:
   ```bash
   bash config/semgrep/tests/run_tests.sh
   ```

This is the level of adaptation the root `README.md` warning is asking for — the demo bundle is a starting point, and stacks it doesn't already model (like Go here) need rules written from scratch, not just folder selection.
```

- [ ] **Step 2: Verify the referenced rule pattern is syntactically valid Semgrep (spot-check)**

```bash
cd ~/projects/poh-org/poh-security-agent
mkdir -p /tmp/go-rule-check
cat > /tmp/go-rule-check/unchecked-error.yaml << 'EOF'
rules:
  - id: unchecked-error-return
    languages: [go]
    severity: WARNING
    message: "Error return value is not checked"
    patterns:
      - pattern: $FUNC(...)
      - pattern-not: $ERR = $FUNC(...)
      - pattern-not: $VAL, $ERR = $FUNC(...)
EOF
semgrep --validate --config /tmp/go-rule-check/unchecked-error.yaml
rm -rf /tmp/go-rule-check
```
Expected: validation succeeds (no `invalid configuration file` error). If it fails, fix the YAML in both the temp file and the example doc, re-run until valid.

- [ ] **Step 3: Commit**

```bash
cd ~/projects/poh-org/poh-security-agent
rm -f examples/.gitkeep
git add examples/personalized-config-example.md
git rm --cached examples/.gitkeep 2>/dev/null || true
git commit -m "docs: add worked personalization example for a non-demo stack"
```

---

### Task 10: Re-verify README links, create GitHub repo, push

**Files:**
- Modify: none (verification + publish task)

**Interfaces:**
- Consumes: entire repo state from Tasks 1–9
- Produces: public repo `po-helper-org/poh-security-agent` on GitHub with all commits pushed

- [ ] **Step 1: Re-run the README link check now that Task 9 exists**

```bash
cd ~/projects/poh-org/poh-security-agent
for f in AGENTS.md LICENSE skills/security-audit/SKILL.md skills/security-setup/SKILL.md workflows/semgrep-full.yml workflows/semgrep-pr.yml config/semgrep/base/temporal-determinism.yaml config/semgrep/README.md examples/personalized-config-example.md; do
  [ -f "$f" ] && echo "OK $f" || echo "MISSING $f"
done
```
Expected: every line reads `OK ...`. Fix any `MISSING` before proceeding.

- [ ] **Step 2: Full-repo sanity pass — validate every rule file and run the suite one more time**

```bash
cd ~/projects/poh-org/poh-security-agent
find config/semgrep -name "*.yaml" -type f -exec semgrep --validate --config {} \;
bash config/semgrep/tests/run_tests.sh
actionlint workflows/semgrep-full.yml workflows/semgrep-pr.yml .github/workflows/test-rules.yml
```
Expected: all `--validate` calls succeed, `run_tests.sh` prints `All tests passed!`, `actionlint` produces no output.

- [ ] **Step 3: Confirm working tree is clean**

Run: `git status --short`
Expected: empty output (everything committed)

- [ ] **Step 4: Create the GitHub repo under po-helper-org and push**

```bash
cd ~/projects/poh-org/poh-security-agent
gh repo create po-helper-org/poh-security-agent --public \
  --description "Autonomous Semgrep-based security-audit toolkit for AI agent harnesses" \
  --source . --remote origin --push
```
Expected: command prints the new repo URL (`https://github.com/po-helper-org/poh-security-agent`) and pushes the current branch.

- [ ] **Step 5: Verify the push landed and CI trigger fires**

```bash
gh repo view po-helper-org/poh-security-agent --web=false
gh run list --repo po-helper-org/poh-security-agent --limit 5
```
Expected: `gh repo view` prints repo metadata without error; `gh run list` shows a run for `test-rules.yml` (may show `in_progress` or `queued` — that's fine, it confirms the workflow file was recognized and triggered by the push).
