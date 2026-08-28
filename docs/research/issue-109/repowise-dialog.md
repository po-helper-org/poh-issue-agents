---
session: rw-openhands-po-helper-org__poh-issue-agents-109
workspace: contour
turns: 10
started: 2026-08-21T16:43:49Z
finished: 2026-08-21T16:47:49Z
---

# Свежесть индекса

| репозиторий | SHA | возраст индекса |
|---|---|---|
| `poh-bft-writer` | `c7fe9bd7d1b2` | 23 мин |
| `poh-cortex` | `3c3e1a3a9e83` | 23 мин |
| `poh-helper` | `18512c1e7ce9` | 23 мин |
| `poh-infra` | `a1db4f02f10c` | 23 мин |
| `poh-issue-agents` | `230d40231d62` | 23 мин |
| `poh-memory-engine` | `194e39319b3f` | 23 мин |
| `poh-pr-agents` | `9f15ada9e4e9` | 23 мин |
| `poh-scheduller` | `04cc3f47aff9` | 23 мин |
| `poh-sprint-agents` | `c41cb5b2ce18` | 23 мин |
| `poh-demo-checkout` | `2e7c62aa955e` | 1 сут |

# Диалог

## Ход 1 · `get_overview` · contour

**Запрос:**

```json
{
  "include": "[\"content\"]"
}
```

**Ответ:**

{
  "title": "Repository Overview: poh-issue-agents",
  "content_md": "# Repository Overview: poh-issue-agents\n\n**Files:** 323 | **Lines:** 80733 | **Import cycles:** 1\n\n## Project Summary\n\n\n`poh-issue-agents` is a markdown codebase of 323 files. Execution starts at `webhook/main.py`, `.claude/skills/brainstorming/scripts/server.cjs`.\n\n\n\n\n## Entry Points\nStart here when reading the codebase.\n\n\n- `webhook/main.py`\n\n- `.claude/skills/brainstorming/scripts/server.cjs`\n\n\n\n\n## Primary Execution Flows\n\n- `worker/workflows.py::IssueLifecycle::run` (5 steps)\n\n- `webhook/main.py::github_webhook` (3 steps)\n\n- `worker/workflows.py::IssueAnalysis::run` (3 steps)\n\n- `webhook/main.py::agent_event` (3 steps)\n\n- `worker/github_client.py::dispatch_workflow` (6 steps)\n\n\n\n\n\n\n## Most Central Files\nRanked by PageRank over the import graph: the files most of the codebase ultimately depends on.\n\n- `tests/conftest.py` (0.0634)\n\n- `shared/workflow_types.py` (0.0442)\n\n- `worker/estimation.py` (0.0293)\n\n- `shared/__init__.py` (0.0190)\n\n- `worker/activities.py` (0.0170)\n\n- `tests/test_estimate_activities.py` (0.0155)\n\n- `tests/test_estimate_report.py` (0.0155)\n\n- `tests/test_estimation_compute.py` (0.0155)\n\n- `worker/github_client.py` (0.0125)\n\n- `shared/lifecycle.py` (0.0109)\n\n- `shared/workflow_ids.py` (0.0108)\n\n- `worker/worker.py` (0.0106)\n\n- `worker/workflows.py` (0.0099)\n\n- `shared/labels.py` (0.0095)\n\n- `worker/consolidation_activities.py` (0.0093)\n\n- `webhook/main.py` (0.0090)\n\n- `shared/agent_comment.py` (0.0089)\n\n- `shared/temporal_client.py` (0.0084)\n\n- `shared/commands.py` (0.0082)\n\n- `shared/bft.py` (0.0072)\n\n\n\n\n\n\n\n\n\n## Codebase health signals\n- **Hotspots:** 24 files are both high-churn and high-complexity\n- **Stable core:** 0 files unchanged in 90+ days\n- **Most changed (90d):** `worker/activities.py`, `worker/workflows.py`, `worker/worker.py`\n- **Oldest file:** `shared/__init__.py` (38 days)\n\n\n---\n\n*Built from the code's structure. It states what is there, not why it is that\nway. Add an API key and run `repowise generate` to have that written.*\n\n## Architecture map\n\n```mermaid\nflowchart LR\n  subgraph layer_application[\"Application\"]\n    direction TB\n    module_application[\"Application\"]\n  end\n  subgraph layer_config[\"Config\"]\n    direction TB\n    module_claude_skills[\".claude/skills\"]\n    module_claude_commands[\".claude/commands\"]\n  end\n  subgraph layer_utility[\"Utility\"]\n    direction TB\n    module_shared[\"shared\"]\n  end\n  subgraph layer_docs_tooling[\"Docs & Tooling\"]\n    direction TB\n    module_docs_tooling[\"Docs & Tooling\"]\n  end\n  subgraph layer_test[\"Test\"]\n    direction TB\n    module_test[\"Test\"]\n  end\n\n  module_application -->|\"39\"| module_shared\n  module_docs_tooling -->|\"14\"| module_shared\n```\n",
  "code_health": {
    "average_health": 8.36,
    "band": "healthy",
    "hotspot_health": 5.01,
    "worst_performer_path": "worker/workflows.py",
    "worst_performer_score": 1.0,
    "open_findings": 461,
    "file_count": 350,
    "distribution": {
      "total_files": 350,
      "total_nloc": 50825,
      "bands": {
        "healthy": {
          "files": 311,
          "nloc": 37752,
          "pct": 74.3
        },
        "warning": {
          "files": 35,
          "nloc": 7959,
          "pct": 15.7
        },
        "alert": {
          "files": 4,
          "nloc": 5114,
          "pct": 10.1
        }
      }
    }
  },
  "key_modules": [
    {
      "name": "Architecture Scripts",
      "path": ".claude/skills/architecture/scripts",
      "description": "`.claude/skills/architecture/scripts` · `.claude/skills/brainstorming/scripts` · `.claude/skills/systematic-debugging` · `.claude/skills/writing-skills`\n\n**Language:** javascript | **Files:** 5 |…",
      "page_id": "module_page:.claude/skills/architecture/scripts",
      "section": "4",
      "parent_page_id": "repo_overview:poh-issue-agents"
    },
    {
      "name": "Docs Tooling Scripts",
      "path": "scripts",
      "description": "`scripts`\n\n**Language:** python | **Files:** 8 | **Public symbols:** 49 / 51\n\n\nCovers the 8 source files in scripts. Does not cover code outside those directories, which is documented on its own…",
      "page_id": "module_page:scripts",
      "section": "5",
      "parent_page_id": "repo_overview:poh-issue-agents"
    },
    {
      "name": "Utility Shared",
      "path": "shared",
      "description": "`shared`\n\n**Language:** python | **Files:** 18 | **Public symbols:** 236 / 256\n\n\nCovers the 18 source files in shared. Does not cover code outside those directories, which is documented on its own…",
      "page_id": "module_page:shared",
      "section": "6",
      "parent_page_id": "repo_overview:poh-issue-agents"
    },
    {
      "name": "Application Webhook",
      "path": "webhook",
      "description": "`webhook`\n\n**Language:** python | **Files:** 1 | **Public symbols:** 9 / 21\n\n\nCovers the 1 source files in webhook. Does not cover code outside those directories, which is documented on its own…",
      "page_id": "module_page:webhook",
      "section": "7",
      "parent_page_id": "repo_overview:poh-issue-agents"
    },
    {
      "name": "Application Worker",
      "path": "worker",
      "description": "`worker`\n\n**Language:** python | **Files:** 9 | **Public symbols:** 190 / 294\n\n\nCovers the 9 source files in worker. Does not cover code outside those directories, which is documented on its own…",
      "page_id": "module_page:worker",
      "section": "8",
      "parent_page_id": "repo_overview:poh-issue-agents"
    }
  ],
  "entry_points": [
    "webhook/main.py",
    ".claude/skills/brainstorming/scripts/server.cjs"
  ],
  "git_health": {
    "files_git_attributed": 353,
    "hotspot_count": 40,
    "avg_bus_factor": 0.6,
    "files_with_bus_factor_1": 109,
    "churn_trend": "increasing",
    "top_churn_modules": [
      ".claude/skills",
      "worker/activities.py",
      "worker/workflows.py",
      "README.md",
      "worker/worker.py"
    ]
  },
  "knowledge_map": {
    "top_owners": [
      {
        "name": "kibarik",
        "files_owned": 82,
        "percentage": 23.2
      },
      {
        "name": "kibarik",
        "files_owned": 71,
        "percentage": 20.1
      },
      {
        "name": "Claude",
        "files_owned": 6,
        "percentage": 1.7
      }
    ]
  },
  "community_summary": [
    {
      "id": 0,
      "label": "tests",
      "size": 13
    },
    {
      "id": 1,
      "label": "tests (31)",
      "size": 11
    },
    {
      "id": 2,
      "label": "tests (35)",
      "size": 8
    },
    {
      "id": 3,
      "label": "server",
      "size": 7
    },
    {
      "id": 4,
      "label": "external:~/threads",
      "size": 3
    },
    {
      "id": 5,
      "label": "tests (5)",
      "size": 3
    },
    {
      "id": 6,
      "label": "claude",
      "size": 1
    },
    {
      "id": 7,
      "label": "installed_skills",
      "size": 1
    },
    {
      "id": 8,
      "label": "commands",
      "size": 1
    },
    {
      "id": 9,
      "label": "commands (1)",
      "size": 1
    }
  ],
  "outline": {
    "root": {
      "page_id": "repo_overview:poh-issue-agents",
      "title": "Repository Overview: poh-issue-agents"
    },
    "total_pages": 252,
    "sections": [
      {
        "section": "1",
        "page_id": "onboarding:onboarding/key_concepts",
        "title": "Key Concepts",
        "page_type": "onboarding",
        "target_path": "onboarding/key_concepts"
      },
      {
        "section": "2",
        "page_id": "onboarding:onboarding/how_it_works",
        "title": "How It Works",
        "page_type": "onboarding",
        "target_path": "onboarding/how_it_works"
      },
      {
        "section": "3",
        "page_id": "onboarding:onboarding/active_landscape",
        "title": "Active Landscape",
        "page_type": "onboarding",
        "target_path": "onboarding/active_landscape"
      },
      {
        "section": "4",
        "page_id": "module_page:.claude/skills/architecture/scripts",
        "title": "Architecture Scripts",
        "page_type": "module_page",
        "target_path": ".claude/skills/architecture/scripts",
        "descendants": 5
      },
      {
        "section": "5",
        "page_id": "module_page:scripts",
        "title": "Docs Tooling Scripts",
        "page_type": "module_page",
        "target_path": "scripts",
        "descendants": 8
      },
      {
        "section": "6",
        "page_id": "module_page:shared",
        "title": "Utility Shared",
        "page_type": "module_page",
        "target_path": "shared",
        "descendants": 45
      },
      {
        "section": "7",
        "page_id": "module_page:webhook",
        "title": "Application Webhook",
        "page_type": "module_page",
        "target_path": "webhook",
        "descendants": 2
      },
      {
        "section": "8",
        "page_id": "module_page:worker",
        "title": "Application Worker",
        "page_type": "module_page",
        "target_path": "worker",
        "descendants": 102
      },
      {
        "section": "9",
        "page_id": "scc_page:scc-37580294ed84",
        "title": "Circular Dependency: Tests",
        "page_type": "scc_page",
        "target_path": "scc-37580294ed84"
      },
      {
        "section": "10",
        "page_id": "infra_page:.claude/skills/brainstorming/scripts/start-server.sh",
        "title": "Infrastructure: .claude/skills/brainstorming/scripts/start-server.sh",
        "page_type": "infra_page",
        "target_path": ".claude/skills/brainstorming/scripts/start-server.sh"
      },
      {
        "section": "11",
        "page_id": "infra_page:.claude/skills/brainstorming/scripts/stop-server.sh",
        "title": "Infrastructure: .claude/skills/brainstorming/scripts/stop-server.sh",
        "page_type": "infra_page",
        "target_path": ".claude/skills/brainstorming/scripts/stop-server.sh"
      },
      {
        "section": "12",
        "page_id": "infra_page:.claude/skills/subagent-driven-development/scripts/review-package",
        "title": "Infrastructure: .claude/skills/subagent-driven-development/scripts/review-package",
        "page_type": "infra_page",
        "target_path": ".claude/skills/subagent-driven-development/scripts/review-package"
      },
      {
        "section": "13",
        "page_id": "infra_page:.claude/skills/subagent-driven-development/scripts/sdd-workspace",
        "title": "Infrastructure: .claude/skills/subagent-driven-development/scripts/sdd-workspace",
        "page_type": "infra_page",
        "target_path": ".claude/skills/subagent-driven-development/scripts/sdd-workspace"
      },
      {
        "section": "14",
        "page_id": "infra_page:.claude/skills/subagent-driven-development/scripts/task-brief",
        "title": "Infrastructure: .claude/skills/subagent-driven-development/scripts/task-brief",
        "page_type": "infra_page",
        "target_path": ".claude/skills/subagent-driven-development/scripts/task-brief"
      },
      {
        "section": "15",
        "page_id": "infra_page:.claude/skills/systematic-debugging/find-polluter.sh",
        "title": "Infrastructure: .claude/skills/systematic-debugging/find-polluter.sh",
        "page_type": "infra_page",
        "target_path": ".claude/skills/systematic-debugging/find-polluter.sh"
      },
      {
        "section": "16",
        "page_id": "infra_page:.claude/skills/technical-documentation/scripts/find_sql_queries.sh",
        "title": "Infrastructure: .claude/skills/technical-documentation/scripts/find_sql_queries.sh",
        "page_type": "infra_page",
        "target_path": ".claude/skills/technical-documentation/scripts/find_sql_queries.sh"
      },
      {
        "section": "17",
        "page_id": "infra_page:Makefile",
        "title": "Infrastructure: Makefile",
        "page_type": "infra_page",
        "target_path": "Makefile"
      },
      {
        "section": "18",
        "page_id": "infra_page:openhands/Dockerfile",
        "title": "Infrastructure: openhands/Dockerfile",
        "page_type": "infra_page",
        "target_path": "openhands/Dockerfile"
      },
      {
        "section": "19",
        "page_id": "symbol_spotlight:tests/conftest.py::ROOT",
        "title": "Symbol: tests.conftest.ROOT",
        "page_type": "symbol_spotlight",
        "target_path": "tests/conftest.py::ROOT"
      },
      {
        "section": "20",
        "page_id": "symbol_spotlight:tests/conftest.py::RULES_PATH",
        "title": "Symbol: tests.conftest.RULES_PATH",
        "page_type": "symbol_spotlight",
        "target_path": "tests/conftest.py::RULES_PATH"
      },
      {
        "section": "21",
        "page_id": "symbol_spotlight:tests/conftest.py::rules",
        "title": "Symbol: tests.conftest.rules",
        "page_type": "symbol_spotlight",
        "target_path": "tests/conftest.py::rules"
      },
      {
        "section": "22",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::FakeGitHub",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::FakeGitHub"
      },
      {
        "section": "23",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::__init__",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.__init__",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::__init__"
      },
      {
        "section": "24",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::add_label",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.add_label",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::add_label"
      },
      {
        "section": "25",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::add_reaction",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.add_reaction",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::add_reaction"
      },
      {
        "section": "26",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::branch_exists",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.branch_exists",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::branch_exists"
      },
      {
        "section": "27",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::comment",
        "title": "Symbol: tests.test_estimate_activities.comment",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::comment"
      },
      {
        "section": "28",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::fake",
        "title": "Symbol: tests.test_estimate_activities.fake",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::fake"
      },
      {
        "section": "29",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::get_file",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.get_file",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::get_file"
      },
      {
        "section": "30",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::get_issue",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.get_issue",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::get_issue"
      },
      {
        "section": "31",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::list_comments",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.list_comments",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::list_comments"
      },
      {
        "section": "32",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::post_comment",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.post_comment",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::post_comment"
      },
      {
        "section": "33",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_ack_puts_eyes_on_the_command_comment",
        "title": "Symbol: tests.test_estimate_activities.test_ack_puts_eyes_on_the_command_comment",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_ack_puts_eyes_on_the_command_comment"
      },
      {
        "section": "34",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_bot_comments_and_commands_are_excluded_from_the_thread",
        "title": "Symbol: tests.test_estimate_activities.test_bot_comments_and_commands_are_excluded_from_the_thread",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_bot_comments_and_commands_are_excluded_from_the_thread"
      },
      {
        "section": "35",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_bug_branch_is_used_when_there_is_no_research_branch",
        "title": "Symbol: tests.test_estimate_activities.test_bug_branch_is_used_when_there_is_no_research_branch",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_bug_branch_is_used_when_there_is_no_research_branch"
      },
      {
        "section": "36",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_compute_activity_returns_rendered_markdown",
        "title": "Symbol: tests.test_estimate_activities.test_compute_activity_returns_rendered_markdown",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_compute_activity_returns_rendered_markdown"
      },
      {
        "section": "37",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_context_carries_title_body_and_labels",
        "title": "Symbol: tests.test_estimate_activities.test_context_carries_title_body_and_labels",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_context_carries_title_body_and_labels"
      },
      {
        "section": "38",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_error_reports_the_stage_and_reacts",
        "title": "Symbol: tests.test_estimate_activities.test_error_reports_the_stage_and_reacts",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_error_reports_the_stage_and_reacts"
      },
      {
        "section": "39",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_no_branch_means_no_artifacts_and_is_not_an_error",
        "title": "Symbol: tests.test_estimate_activities.test_no_branch_means_no_artifacts_and_is_not_an_error",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_no_branch_means_no_artifacts_and_is_not_an_error"
      },
      {
        "section": "40",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_oversized_artifact_is_truncated",
        "title": "Symbol: tests.test_estimate_activities.test_oversized_artifact_is_truncated",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_oversized_artifact_is_truncated"
      }
    ],
    "sections_total": 89,
    "sections_truncated": true
  },
  "outline_hint": "The stored page tree — the same outline the web app and the editor extension render. Every 'section' in this response indexes into it, and 'descendants' is how much sits below an entry. Top rung only by default; call get_overview(include=[\"outline\"]) for one level deeper, then get_context on an entry's target_path to read it.",
  "architecture": {
    "layers": [
      {
        "name": "Application",
        "description": "",
        "file_count": 54
      },
      {
        "name": "Config",
        "description": "",
        "file_count": 139
      },
      {
        "name": "Utility",
        "description": "",
        "file_count": 19
      },
      {
        "name": "Docs & Tooling",
        "description": "",
        "file_count": 41
      },
      {
        "name": "Test",
        "description": "",
        "file_count": 97
      }
    ],
    "tour_available": true,
    "tour_step_count": 12,
    "layer_order": [
      "Application",
      "Config",
      "Utility",
      "Docs & Tooling"
    ]
  },
  "reading_order": [
    {
      "order": 1,
      "slot": "project_overview",
      "title": "Repository Overview: poh-issue-agents",
      "page_id": "repo_overview:poh-issue-agents",
      "target_path": "poh-issue-agents",
      "section": null
    },
    {
      "order": 2,
      "slot": "key_concepts",
      "title": "Key Concepts",
      "page_id": "onboarding:onboarding/key_concepts",
      "target_path": "onboarding/key_concepts",
      "section": "1"
    },
    {
      "order": 3,
      "slot": "how_it_works",
      "title": "How It Works",
      "page_id": "onboarding:onboarding/how_it_works",
      "target_path": "onboarding/how_it_works",
      "section": "2"
    },
    {
      "order": 4,
      "slot": "active_landscape",
      "title": "Active Landscape",
      "page_id": "onboarding:onboarding/active_landscape",
      "target_path": "onboarding/active_landscape",
      "section": "3"
    }
  ],
  "reading_order_hint": "Canonical onboarding sequence — read these page_ids in order via get_context/get_symbol to understand the repo the way a new contributor would.",
  "guided_tour": [
    {
      "order": 1,
      "title": "README.md",
      "kind": "overview",
      "reason": "Start here for the end-to-end picture before diving into the code.",
      "target_path": "README.md",
      "page_id": "repo_overview:README.md",
      "section": null
    },
    {
      "order": 2,
      "title": "main.py",
      "kind": "code",
      "reason": "An entry point — execution and imports fan out from here.",
      "target_path": "webhook/main.py",
      "page_id": "file_page:webhook/main.py",
      "section": "7.2"
    },
    {
      "order": 3,
      "title": "workflow_types.py",
      "kind": "code",
      "reason": "Directly used by the entry points above; a core collaborator.",
      "target_path": "shared/workflow_types.py",
      "page_id": "file_page:shared/workflow_types.py",
      "section": "6.18"
    },
    {
      "order": 9,
      "title": "backfill.py",
      "kind": "code",
      "reason": "The Docs & Tooling layer's anchor — its most depended-on file.",
      "target_path": "scripts/backfill.py",
      "page_id": "file_page:scripts/backfill.py",
      "section": "5.2"
    },
    {
      "order": 10,
      "title": "estimation-rules.toml",
      "kind": "code",
      "reason": "The Config layer's anchor — its most depended-on file.",
      "target_path": "config/estimation-rules.toml",
      "page_id": "file_page:config/estimation-rules.toml",
      "section": null
    },
    {
      "order": 11,
      "title": "activities.py",
      "kind": "code",
      "reason": "A top churn hotspot — one of the most frequently changed files in the repo; worth understanding early.",
      "target_path": "worker/activities.py",
      "page_id": "file_page:worker/activities.py",
      "section": "8.2"
    },
    {
      "order": 12,
      "title": "conftest.py",
      "kind": "code",
      "reason": "The test suite — how the system's behavior is verified.",
      "target_path": "tests/conftest.py",
      "page_id": "file_page:tests/conftest.py",
      "section": null
    }
  ],
  "guided_tour_hint": "Topology-ordered walk of the codebase: read these page_ids in order — entry points first, then the files they import, with infrastructure last. Each step builds on the previous.",
  "workspace": {
    "workspace_root": "/workspaces/contour",
    "default_repo": "poh-issue-agents",
    "other_repos": [
      "poh-bft-writer",
      "poh-cortex",
      "poh-helper",
      "poh-infra",
      "poh-memory-engine",
      "poh-pr-agents",
      "poh-scheduller",
      "poh-sprint-agents"
    ],
    "hint": "This repo is part of a workspace. Other repos: poh-bft-writer, poh-cortex, poh-helper, poh-infra, poh-memory-engine, poh-pr-agents, poh-scheduller, poh-sprint-agents. Use repo='<alias>' to query another repo, or repo='all' for workspace-wide results.",
    "cross_repo": {
      "co_change_count": 78,
      "package_dep_count": 0,
      "top_connections": [
        {
          "repos": [
            "poh-bft-writer",
            "poh-issue-agents"
          ],
          "edge_count": 50
        },
        {
          "repos": [
            "poh-issue-agents",
            "poh-pr-agents"
          ],
          "edge_count": 10
        },
        {
          "repos": [
            "poh-helper",
            "poh-issue-agents"
          ],
          "edge_count": 7
        },
        {
          "repos": [
            "poh-issue-agents",
            "poh-memory-engine"
          ],
          "edge_count": 5
        },
        {
          "repos": [
            "poh-infra",
            "poh-issue-agents"
          ],
          "edge_count": 4
        }
      ]
    },
    "contract_links": {
      "total_contracts": 23,
      "total_links": 0,
      "by_type": {
        "http": 12,
        "data": 11
      }
    }
  },
  "tool_guide": {
    "first_call": "get_answer for any how/where/why question; trust confidence=high directly (it is content-grounded).",
    "reading_code": "get_context(include=[\"skeleton\"]) for a whole file verified, or just Read it. get_symbol only for an id a response already gave you — never file-by-signature.",
    "recipes": [
      "get_answer low confidence → Read best_guesses[0].file",
      "get_context hotspot: true → get_risk before editing",
      "get_context decision_records → get_why(targets=[...]) for rationale",
      "PR review → get_risk(targets, changed_files) and read directive first",
      "search_codebase(query) auto-routes: identifier → symbol hits (pipe symbol_id into get_symbol), path → files (get_context), prose → wiki search. Force with mode=symbol|path|concept|hybrid."
    ],
    "reread_triggers": "Only re-read source on bounds: approximate, stale_warning in _meta, or a search hit whose sources are [fts] only (keyword match, no semantic agreement)."
  },
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "7ba6a6d6301c",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "omitted": {
      "refs": [
        "4b14af6bd067"
      ],
      "tokens": 1960,
      "restore": "Run `repowise expand <ref>` from the repo, or call get_symbol(\"repowise#<ref>\", query=...) to retrieve the omitted content."
    }
  },
  "omission_marker": "[repowise#4b14af6bd067: 53 lines omitted (~1960 tokens); restore: repowise expand 4b14af6bd067]"
}

## Ход 2 · `get_context` · contour

**Запрос:**

```json
{
  "targets": [
    "worker/github_client.py",
    "webhook/main.py",
    "worker/activities.py"
  ],
  "include": "[\"skeleton\"]"
}
```

**Ответ:**

{
  "targets": {
    "worker/github_client.py": {
      "target": "worker/github_client.py",
      "type": "file",
      "parent_page": {
        "title": "Application Worker",
        "target_path": "worker",
        "section": "8"
      },
      "docs": {
        "title": "File: worker/github_client.py",
        "summary": "Обёртка над GitHub REST API. В отличие от версии на Actions (которая жила на GITHUB_TOKEN, выданном раннеру автоматически), self-hosted сервис аутентифицируется как GitHub App — токен инсталляции нужно генерировать и обновлять самостоятельно (живёт ~1 час)."
      },
      "hotspot": true,
      "fix_history": {
        "fix_count": 7,
        "last_fix_days_ago": 2,
        "bug_magnet": true
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "stale",
        "is_stale": true
      },
      "architectural_layer": {
        "name": "Application",
        "description": "",
        "role": "edge_connector"
      },
      "skeleton": {
        "mode": "smart",
        "tokens": 1933,
        "full_tokens": 6774,
        "pct_of_full": 28.5,
        "bodies_kept": [
          "_auth_headers",
          "_warn_pat_over_app",
          "_installation_token_for",
          "post_comment",
          "add_label"
        ],
        "text": "\"\"\"\nОбёртка над GitHub REST API. В отличие от версии на Actions (которая жила\nна GITHUB_TOKEN, выданном раннеру автоматически), self-hosted сервис\nаутентифицируется как GitHub App — токен инсталляции нужно генерировать\nи обновлять самостоятельно (живёт ~1 час).\n\"\"\"\n\nimport base64\nimport logging\nimport os\nimport subprocess\nimport threading\nimport time\nimport urllib.parse\n\nimport jwt\nimport requests\n\nfrom shared.agent_comment import is_agent_comment, sign\nfrom shared.labels import ORIGIN_AGENT\n\n_log = logging.getLogger(\"github_client\")\n\n\ndef _dry_run() -> bool:\n    ... 7 lines (26-32)\n_token_cache: dict[str, tuple[str, float]] = {}\n_token_lock = threading.Lock()\n\n\ndef _app_private_key() -> bytes:\n    \"\"\"Приватный ключ App: из GITHUB_PRIVATE_KEY_B64 (base64→PEM), иначе из файла\n    ... 6 lines (39-44)\n\n\ndef _app_jwt() -> str:\n    ... 3 lines (48-50)\n\n\ndef _cached_token(repo: str) -> str | None:\n    ... 4 lines (54-57)\n\n\ndef _installation_token_for(repo: str) -> str:\n    \"\"\"Installation-токен под установку App на данный репозиторий. Установка\n    определяется по репо (не хардкод GITHUB_INSTALLATION_ID): App не установлен →\n    GET /repos/{repo}/installation вернёт 404 и вызов упадёт.\n\n    Double-checked locking: горячий путь (кэш валиден) не берёт lock, поэтому\n    cache-hit по одному репо не блокируется за token-обменом другого. Lock\n    сериализует только сам обмен (редкий — раз в ~55 мин на репо).\"\"\"\n    hot = _cached_token(repo)\n    if hot is not None:\n        return hot\n    with _token_lock:\n        warm = _cached_token(repo)  # перепроверка под lock: конкурент мог уже выпустить\n        if warm is not None:\n            return warm\n        app_headers = {\"Authorization\": f\"Bearer {_app_jwt()}\",\n                       ... 13 lines (76-88)\n\n\ndef _installation_token_headers(repo: str) -> dict:\n    return {\"Authorization\": f\"Bearer {_installation_token_for(repo)}\",\n            \"Accept\": \"application/vnd.github+json\"}\n\n\n_pat_over_app_warned = False\n\n\ndef _warn_pat_over_app() -> None:\n    \"\"\"Один раз на процесс: PAT задан вместе с App и молча его отключает.\n\n    Симптом на стороне GitHub — всё постится от имени владельца токена, а не от\n    приложения, и понять это по поведению нельзя. Одиночный PAT — штатный\n    dev-фолбэк, он молчит; предупреждаем только про КОНФЛИКТ настроек.\n    Предупреждение одноразовое: _auth_headers зовётся на каждый REST-вызов.\n    \"\"\"\n    global _pat_over_app_warned\n    if _pat_over_app_warned:\n        return\n    _pat_over_app_warned = True\n    _log.warning(\n        \"GH_TOKEN/GITHUB_TOKEN задан одновременно с GITHUB_APP_ID: GitHub App НЕ \"\n        \"используется, все действия идут от имени владельца токена. Убери PAT, \"\n        \"если ожидаешь работу от приложения (см. scripts/diag.py).\"\n    )\n\n\ndef _auth_headers(repo: str) -> dict:\n    \"\"\"PAT path for the pilot: if GH_TOKEN/GITHUB_TOKEN is set, use it directly\n    (repo-agnostic) and skip the GitHub App flow. Otherwise per-repo App auth.\"\"\"\n    token = os.environ.get(\"GH_TOKEN\") or os.environ.get(\"GITHUB_TOKEN\")\n    if token:\n        if os.environ.get(\"GITHUB_APP_ID\"):\n            _warn_pat_over_app()\n        return {\"Authorization\": f\"Bearer {token}\", \"Accept\": \"application/vnd.github+json\"}\n    return _installation_token_headers(repo)\n\n\ndef post_comment(repo: str, issue_number: int, body: str) -> None:\n    \"\"\"Комментарий сервиса — всегда подписанный.\n\n    Подпись ставится здесь, в единственной точке отправки, а не в каждом месте,\n    где текст собирается: пропущенная подпись означала бы, что вебхук примет наш\n    комментарий за ответ человека и накормит им цикл уточнений (см.\n    shared/agent_comment.py).\n    \"\"\"\n    body = sign(body)\n    if _dry_run():\n        _log.info(\"[DRY_RUN] comment %s#%s: %s\", repo, issue_number, body[:200])\n        ... 4 lines (140-143)\n\n\ndef add_label(repo: str, issue_number: int, label: str) -> None:\n    if _dry_run():\n        _log.info(\"[DRY_RUN] label %s#%s += %s\", repo, issue_number, label)\n        return\n    url = f\"https://api.github.com/repos/{repo}/issues/{issue_number}/labels\"\n    resp = requests.post(url, headers=_auth_headers(repo), json={\"labels\": [label]}, timeout=30)\n    resp.raise_for_status()\n\n\ndef remove_label(repo: str, issue_number: int, label: str) -> None:\n    \"\"\"Снимает метку. Отсутствующая метка (404) — штатная ситуация, а не ошибка:\n    ... 15 lines (157-171)\n\n\ndef create_issue(repo: str, title: str, body: str, labels: list[str] | None = None) -> int:\n    \"\"\"Создаёт Issue и возвращает его номер.\n... 15 lines (176-190)\n\n\ndef close_issue(repo: str, issue_number: int) -> None:\n    ... 6 lines (194-199)\n\n\ndef search_candidates(repo: str, query: str, limit: int = 15) -> list[dict]:\n    \"\"\"Через gh CLI — тот же паттерн, что и в версии на Actions, но токен\n    ... 14 lines (204-217)\n\n\ndef branch_exists(repo: str, branch: str) -> bool:\n    ... 3 lines (221-223)\n\n\ndef auth_token(repo: str) -> str:\n    \"\"\"Голый токен для внешних процессов (git clone, gh CLI).\n... 4 lines (228-231)\n\n\ndef add_reaction(repo: str, comment_id: int, content: str = \"eyes\") -> None:\n    \"\"\"Реакция на комментарий — видимое «команда принята» до тяжёлой работы.\n    ... 7 lines (236-242)\n\n\ndef ensure_branch(repo: str, branch: str) -> None:\n    \"\"\"Создаёт ветку от дефолтной, если её ещё нет.\"\"\"\n    ... 23 lines (247-269)\n\n\ndef put_file(repo: str, branch: str, path: str, content: str, message: str) -> None:\n    \"\"\"Создаёт или обновляет файл в ветке через Contents API.\n... 19 lines (274-292)\n\n\ndef push_artifacts_to_branch(repo: str, branch: str, files: dict[str, str], message: str) -> None:\n    \"\"\"Публикует артефакты (путь -> содержимое) в ветку одним проходом.\"\"\"\n    ... 7 lines (297-303)\n\n\ndef get_issue(repo: str, issue_number: int) -> dict:\n    ... 4 lines (307-310)\n\n\ndef list_comments(repo: str, issue_number: int, limit: int = 50) -> list[dict]:\n    ... 6 lines (314-319)\n\n\ndef list_linked_prs(repo: str, issue_number: int, limit: int = 20) -> list[dict]:\n    \"\"\"PR, кросс-ссылающиеся на issue (Timeline API).\n... 35 lines (324-358)\n\n\ndef get_file(repo: str, path: str, ref: str) -> str | None:\n    \"\"\"Содержимое файла из ветки. None — файла нет; для артефактов это\n    ... 11 lines (363-373)\n\n\ndef create_pr_with_files(repo: str, branch: str, base: str,\n                         files: dict, title: str, body: str):\n    ... 32 lines (378-409)\n\n\ndef list_open_issues(repo: str, limit: int = 300) -> list:\n    ... 16 lines (413-428)\n\n\ndef get_issue_body(repo: str, issue_number: int) -> str:\n    ... 4 lines (432-435)\n\n\ndef dispatch_workflow(repo: str, workflow_file: str, ref: str, inputs: dict) -> None:\n    \"\"\"Запускает workflow репозитория-цели через `workflow_dispatch`.\n... 18 lines (440-457)\n\n\nclass GitCommandError(RuntimeError):\n    \"\"\"Отказ git с сохранённой причиной.\n... 6 lines (462-467)\n\n\ndef _git_runner(clone_dir: str, env: dict):\n    \"\"\"git по рабочему дереву задачи, с видимой причиной отказа.\n... 19 lines (472-490)\n\n\ndef publish_worktree(repo: str, clone_dir: str, branch: str, *,\n                     title: str, body: str, message: str) -> int | None:\n    \"\"\"Коммит рабочего дерева в ветку и PR. None — изменений нет.\n... 67 lines (496-562)\n\n\ndef _default_branch(repo: str) -> str:\n    ... 4 lines (566-569)\n\n\ndef get_pull(repo: str, number: int) -> dict:\n    ... 4 lines (573-576)\n\n\ndef review_text(repo: str, number: int, limit: int = 12000) -> str:\n    \"\"\"Замечания ревью одним текстом: обзорные комментарии + построчные.\n... 42 lines (581-622)\n\n\ndef push_fixes(repo: str, clone_dir: str, branch: str, message: str) -> bool:\n    \"\"\"Коммит правок в ветку PR. False — агент ничего не изменил.\n... 31 lines (627-657)\n\n\ndef update_issue_body(repo: str, issue_number: int, body: str) -> None:\n    ... 6 lines (661-666)\n",
        "verified": true
      },
      "episodes": 7,
      "cross_repo": {
        "co_changes_with": [
          {
            "repo": "poh-memory-engine",
            "file": "README.md",
            "strength": 0.624
          }
        ]
      }
    },
    "webhook/main.py": {
      "target": "webhook/main.py",
      "type": "file",
      "parent_page": {
        "title": "Application Webhook",
        "target_path": "webhook",
        "section": "7"
      },
      "docs": {
        "title": "File: webhook/main.py",
        "summary": "Webhook receiver: единственная точка входа для GitHub. Проверяет подпись, транслирует событие в вызов Temporal:"
      },
      "hotspot": true,
      "fix_history": {
        "fix_count": 4,
        "last_fix_days_ago": 2,
        "bug_magnet": true
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "stale",
        "is_stale": true
      },
      "architectural_layer": {
        "name": "Application",
        "description": "",
        "role": "edge_connector"
      },
      "skeleton": {
        "mode": "smart",
        "tokens": 2046,
        "full_tokens": 6855,
        "pct_of_full": 29.8,
        "bodies_kept": [
          "_client_disconnect",
          "_log_effective_config",
          "verify_agent_signature",
          "_report_orphan",
          "_lifecycle_args_for"
        ],
        "text": "[repowise#31511851a0c8: 203 lines omitted (~2046 tokens); restore: repowise expand 31511851a0c8]",
        "verified": true,
        "omitted": true
      },
      "episodes": 4
    },
    "worker/activities.py": {
      "target": "worker/activities.py",
      "type": "file",
      "parent_page": {
        "title": "Application Worker",
        "target_path": "worker",
        "section": "8"
      },
      "docs": {
        "title": "File: worker/activities.py",
        "summary": "Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на GitHub Actions)."
      },
      "hotspot": true,
      "fix_history": {
        "fix_count": 21,
        "last_fix_days_ago": 0,
        "bug_magnet": true
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "fresh",
        "is_stale": false
      },
      "architectural_layer": {
        "name": "Application",
        "description": "",
        "role": "edge_connector"
      },
      "skeleton": {
        "mode": "smart",
        "tokens": 5932,
        "full_tokens": 34578,
        "pct_of_full": 17.2,
        "bodies_kept": [],
        "text": "[repowise#477d02ee2a6f: 765 lines omitted (~5932 tokens); restore: repowise expand 477d02ee2a6f]",
        "verified": true,
        "omitted": true
      },
      "episodes": 21
    }
  },
  "_meta": {
    "timing_ms": 417.4,
    "index_age_days": 0,
    "indexed_commit": "7ba6a6d6301c",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "omitted": {
      "refs": [
        "477d02ee2a6f",
        "31511851a0c8"
      ],
      "tokens": 7978,
      "restore": "Run `repowise expand <ref>` from the repo, or call get_symbol(\"repowise#<ref>\", query=...) to retrieve the omitted content."
    }
  },
  "truncated": true,
  "dropped_targets": [],
  "dropped_symbols": {}
}

## Ход 3 · `get_answer` · contour

**Запрос:**

```json
{
  "question": "How does the current authentication and authorization work in the webhook and worker? What are the main GitHub-specific assumptions in the codebase?"
}
```

**Ответ:**

{
  "answer": "No synthesized prose (no-llm-provider), but retrieval succeeded and this payload is usable: 5 ranked hits in `retrieval`, the files to open in `fallback_targets`, and the wider ranked shortlist in `candidates`. Read those rather than starting a fresh search.",
  "citations": [],
  "confidence": "low",
  "retrieval_quality": "high",
  "degraded": "no-llm-provider",
  "fallback_targets": [
    "webhook/main.py",
    "worker/github_client.py",
    "shared/workflow_types.py",
    "worker/activities.py",
    "worker/worker.py"
  ],
  "retrieval": [
    {
      "path": "webhook/main.py",
      "title": "File: webhook/main.py",
      "summary": "Webhook receiver: единственная точка входа для GitHub. Проверяет подпись, транслирует событие в вызов Temporal:",
      "snippet": "# webhook/main.py\n\n## Overview\n\nWebhook receiver: единственная точка входа для GitHub. Проверяет подпись,\nтранслирует событие в вызов Temporal:\n- issues.opened            -> старт нового workflow (ID",
      "excerpt": "# webhook/main.py\n\n## Overview\n\nWebhook receiver: единственная точка входа для GitHub. Проверяет подпись,\nтранслирует событие в вызов Temporal:\n- issues.opened            -> старт нового workflow (ID = repo-issue-N)\n- issue_comment.created    -> `/analyze` запускает workflow IssueAnalysis и\n                               через signal-with-start поднимает цикл-владелец\n                               состояния, `/estimate` — IssueEstimation,\n                               `/bft` и `/bft-deep` — IssueBft (хвост команды\n                               уезжает в прогон как замечания/уточнения); любой\n                               другой комментарий — сигнал уже идущему workflow\n                               (используется циклом уточнений)\n- issues.labeled           -> `run:<команда>` запускает тот же воркфлоу, что и\n                               команда в комментарии (run:analyze ->\n                               IssueAnalysis, run:estimate -> IssueEstimation,\n                               run:bft / run:bft-deep -> IssueBft);\n                               точки решения человека (research-me / bug-me /\n                               build-me) идут через signal-with-start: воркфлоу\n                               триажа может не существовать, тогда он\n                               поднимается тем же вызовом\n\nНичего из бизнес-логики здесь нет — это чистый транспортный слой.\n\nIt exposes 9 public symbols and depends on 12 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n|",
      "score": 2.868,
      "key_symbols": [
        {
          "name": "_log",
          "kind": "variable",
          "signature": "_log = logging.getLogger(\"webhook\")",
          "docstring": "",
          "start_line": 62,
          "end_line": 62,
          "source_excerpt": "_log = logging.getLogger(\"webhook\")"
        },
        {
          "name": "app",
          "kind": "variable",
          "signature": "app = FastAPI()",
          "docstring": "",
          "start_line": 64,
          "end_line": 64
        },
        {
          "name": "_client_disconnect",
          "kind": "function",
          "signature": "async def _client_disconnect(request: Request, exc: ClientDisconnect):",
          "docstring": "Отправитель ушёл, не дослав тело.\n\n    Отвечать 500 некому: соединения уже нет, а событие уезжает в Sentry как\n    сбой вебхука (ISSUE-AGENT-8, пять штук за один разрыв связи с прокси).\n    Доставка не потеряна — GitHub ретраит её сам, так что здесь нечего чинить\n    и не о чем будить. 204 закрывает запрос тихо и оставляет след в логе.",
          "start_line": 68,
          "end_line": 78
        },
        {
          "name": "HUMAN_DECISION_LABELS",
          "kind": "constant",
          "signature": "HUMAN_DECISION_LABELS = {\"research-me\", \"bug-me\", \"build-me\", \"not-duplicate\", \"confirm-duplicate\"}",
          "docstring": "",
          "start_line": 81,
          "end_line": 81
        },
        {
          "name": "_log_effective_config",
          "kind": "function",
          "signature": "def _log_effective_config() -> None:",
          "docstring": "Один раз на старте — какой конфиг реально действует.\n\n    Секреты не логируются: только режим авторизации. Полная картина —\n    `scripts/diag.py` внутри контейнера; эта строка нужна, чтобы после\n    передеплоя не гадать, подхватились ли переменные.",
          "start_line": 84,
          "end_line": 103
        },
        {
          "name": "_temporal_client",
          "kind": "variable",
          "signature": "_temporal_client: Client | None = None",
          "docstring": "",
          "start_line": 108,
          "end_line": 108
        },
        {
          "name": "get_temporal_client",
          "kind": "function",
          "signature": "async def get_temporal_client() -> Client:",
          "docstring": "",
          "start_line": 111,
          "end_line": 115
        },
        {
          "name": "verify_signature",
          "kind": "function",
          "signature": "def verify_signature(body: bytes, signature_header: str | None) -> None:",
          "docstring": "",
          "start_line": 118,
          "end_line": 124
        },
        {
          "name": "_audit_dropped_delivery",
          "kind": "function",
          "signature": "async def _audit_dropped_delivery(payload: dict, event: str, delivery_id: str | None, repo: str, specs: list[str]) -> None:",
          "docstring": "След в Temporal UI для события, отброшенного по allowlist.\n\n    Единственный молчаливый отказ, о котором иначе неоткуда узнать: workflow не\n    создаётся, GitHub получает 200. Аудит-воркфлоу не исполняет ни одной\n    activity — его ценность в том, что вход виден там же, где смотрят всё\n    остальное: пришло, отклонено, вот причина и вот действовавший allowlist.\n\n    Без заголовка X-GitHub-Delivery (ручной curl, тест) аудит пропускаем: без\n    уникального id ретраи GitHub плодили бы дубли. Сбой самого аудита тоже не\n    должен ронять обработку — это диагностика, а не путь события.",
          "start_line": 202,
          "end_line": 237,
          "source_excerpt": "async def _audit_dropped_delivery(payload: dict, event: str, delivery_id: str | None,\n                                  repo: str, specs: list[str]) -> None:\n    \"\"\"След в Temporal UI для события, отброшенного по allowlist.\n\n    Единственный молчаливый отказ, о котором иначе неоткуда узнать: workflow не\n    создаётся, GitHub получает 200. Аудит-воркфлоу не исполняет ни одной\n    activity — его ценность в том, что вход виден там же, где смотрят всё\n    остальное: пришло, отклонено, вот причина и вот действовавший allowlist.\n\n    Без заголовка X-GitHub-Delivery (ручной curl, тест) аудит пропускаем: без\n    уникального id ретраи GitHub плодили бы дубли. Сбой самого аудита тоже не\n    должен ронять обработку — это диагностика, а не путь события.\n    \"\"\"\n    if not delivery_id:\n        return\n    from shared.workflow_types import WebhookAuditInput\n\n    try:\n        client = await get_temporal_client()\n        await client.start_workflow(\n            \"WebhookAudit\",\n            WebhookAuditInput(\n                delivery_id=delivery_id,\n                event=event,\n                action=str(payload.get(\"action\") or \"\"),\n                repo=repo,\n                reason=\"repo_not_allowed\",\n                allowlist=specs,\n            ),\n            id=f\"webhook-drop-{delivery_id}\",\n            task_queue=\"issue-lifecycle\",\n        )\n    except WorkflowAlreadyStartedError:\n        pass  # ретрай той же доставки — запись уже есть\n    except Exception as exc:\n        _log.warning(\"не удалось записать аудит отброшенной доставки: %s\", exc)"
        },
        {
          "name": "github_webhook",
          "kind": "function",
          "signature": "async def github_webhook( request: Request, x_github_event: str = Header(...), x_hub_signature_256: str | None = Header(None),",
          "docstring": "",
          "start_line": 384,
          "end_line": 612,
          "source_excerpt": "async def github_webhook(\n    request: Request,\n    x_github_event: str = Header(...),\n    x_hub_signature_256: str | None = Header(None),\n    x_github_delivery: str | None = Header(None),\n):\n    body = await request.body()\n    verify_signature(body, x_hub_signature_256)\n    payload = await request.json()\n\n    # Allowlist: действуем только на репозитории из ISSUE_AGENT_REPOS (пусто/* —\n    # любой установленный). Чужой репозиторий игнорируем до старта workflow.\n    repo_full = (payload.get(\"repository\") or {}).get(\"full_name\")\n    if repo_full and not is_allowed(repo_full, allowed_specs()):\n        specs = [s for s in allowed_specs() if s.strip()]\n        # warning, а не info, и вместе с действующим allowlist: строка лога\n        # обязана сама говорить, что чинить. Раньше отказ был неотличим от\n        # тишины — GitHub видел 200, в Temporal не появлялось ничего.\n        _log.warning(\n            \"ignored repo %s — not in ISSUE_AGENT_REPOS %s; событие отброшено до Temporal\",\n            repo_full, specs or [\"(пусто)\"],\n        )\n        await _audit_dropped_delivery(payload, x_github_event, x_github_delivery,\n                                      repo_full, specs)\n        return {\"ok\": True}\n\n    client = await get_temporal_client()\n\n    if x_github_event == \"issues\":\n        action = payload[\"action\"]\n        repo = payload[\"repository\"][\"full_name\"]\n        issue_number = payload[\"issue\"][\"number\"]\n        wf_id = workflow_id_for(repo, issue_number)\n\n        if action == \"opened\":\n            try:\n                await client.start_workflow(\n                    \"IssueLifecycle\",  # имя workflow строкой — worker зарегистрирует класс под этим именем\n                    _issue_input(payload, interactive=True),\n                    id=wf_id,\n                    task_queue=\"issue-lifecycle\",\n                    search_attributes=_search_attributes(repo, payload, issue_number),\n                )\n            except WorkflowAlreadyStartedError:\n                # Повторная доставка того же события — норма, а не сбой: GitHub\n                # ретраит, если не дождался ответа, и оба раза просит одного и\n                # того же. Цикл по этому Issue уже существует, то есть нужное\n                # состояние достигнуто.\n                #\n                # 500 здесь был хуже, чем бесполезен: GitHub на нём ретраит\n                # снова, каждый ретрай снова падает, и вебхук отвечает ошибкой\n                # на штатную ситуацию, пока доставка не будет брошена насовсем.\n                _log.info(\"цикл %s#%s уже запущен — повторная доставка\",\n                          repo, issue_number)\n\n        elif action == \"closed\":\n            # Закрытый Issue не ждут. Голый signal, а НЕ signal-with-start:\n            # поднимать цикл по Issue, которым никто не занимался, чтобы тут же\n            # его закрыть, — лишний прогон в истории и лишние вызовы GitHub.\n            handle = client.get_workflow_handle(wf_id)\n            try:\n                await handle.signal(\n                    \"issue_closed\", (payload.get(\"sender\") or {}).get(\"login\"))\n            except Exception:\n                # Цикла нет или он уже завершён — сигналить некому. Это штатно:\n                # на 500 GitHub ретраит доставку и в итоге бросает её насовсем.\n                _log.info(\"no live cycle for closed %s#%s\", repo, issue_number)\n\n        elif action == \"labeled\":\n            label = payload[\"label\"][\"name\"]\n\n            # Метка — второй триггер команды, равноправный с комментарием: два\n            # тапа в мобильном GitHub вместо набора текста в треде. Ведёт в тот\n            # же воркфлоу, что и `/analyze` — таблица соответствия одна\n            # (shared/commands.py), поэтому разъехаться им негде.\n            command = parse_label_command(label)\n\n            if command == ANALYZE:\n                if not _may_start_expensive(payload, label, repo, issue_number):\n                    return {\"ok\": True}\n                # Режим (child цикла или самостоятельный прогон) выбирает\n                # лаунчер — одна точка решения на все входы.\n                await request_analysis(\n                    client,\n                    # Отвечать на уточняющий вопрос тут некому: триггер — метка.\n                    _issue_input(payload, interactive=False),\n                    build_analyze_input(payload),  # без comment_id: триггер — метка\n                    search_attributes=_search_attributes(repo, payload, issue_number),\n                )\n                return {\"ok\": True}\n\n            if command == ESTIMATE:\n                if not _may_start_expensive(payload, label, repo, issue_number):\n                    return {\"ok\": True}\n                from shared.workflow_types import EstimateRequest\n\n                await request_estimate(\n                    client,\n                    _issue_input(payload, interactive=False),\n                    EstimateRequest(repo=repo, issue_number=issue_number),\n                    search_attributes=_search_attributes(repo, payload, issue_number),\n                )\n                return {\"ok\": True}\n\n            if command in (BFT, BFT_DEEP):\n                if not _may_start_expensive(payload, label, repo, issue_number):\n                    return {\"ok\": True}\n                await request_bft(\n                    client,\n                    # Отвечать на уточняющий вопрос тут некому: триггер — метка.\n                    _issue_input(payload, interactive=False),\n                    # Без comment_id и без уточнений: метка несёт только сам факт\n                    # запуска, и это законно — «пересобери по тому, что в Issue».\n                    build_bft_request(payload, bft_mode(command)),\n                    search_attributes=_search_attributes(repo, payload, issue_number),\n                )\n                return {\"ok\": True}\n\n            if label in HUMAN_DECISION_LABELS:\n                if not _may_start_expensive(payload, label, repo, issue_number):\n                    return {\"ok\": True}"
        }
      ]
    },
    {
      "path": "worker/github_client.py",
      "title": "File: worker/github_client.py",
      "summary": "Обёртка над GitHub REST API. В отличие от версии на Actions (которая жила на GITHUB_TOKEN, выданном раннеру автоматически), self-hosted сервис аутентифицируется как GitHub App — токен инсталляции нужно генерировать и обновлять самостоятельно (живёт ~1 час).",
      "snippet": "# worker/github_client.py\n\n## Overview\n\nОбёртка над GitHub REST API. В отличие от версии на Actions (которая жила\nна GITHUB_TOKEN, выданном раннеру автоматически), self-hosted сервис\nаутентифицируется",
      "excerpt": "# worker/github_client.py\n\n## Overview\n\nОбёртка над GitHub REST API. В отличие от версии на Actions (которая жила\nна GITHUB_TOKEN, выданном раннеру автоматически), self-hosted сервис\nаутентифицируется как GitHub App — токен инсталляции нужно генерировать\nи обновлять самостоятельно (живёт ~1 час).\n\nIt exposes 26 public symbols and depends on 2 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `post_comment` | function | def post_comment(repo: str, issue_number: int, body: str) -> None |\n| `add_label` | function | def add_label(repo: str, issue_number: int, label: str) -> None |\n| `remove_label` | function | def remove_label(repo: str, issue_number: int, label: str) -> None |\n| `create_issue` | function | def create_issue(repo: str, title: str, body: str, labels: list[str] \\| None = None) -> int |\n| `close_issue` | function | def close_issue(repo: str, issue_number: int) -> None |\n| `search_candidates` | function | def search_candidates(repo: str, query: str, limit: int = 15) -> list[dict] |\n| `branch_exists` | function | def branch_exists(repo: str, branch: str) -> bool |\n| `auth_token` | function | def auth_token(repo: str) -> str |\n| `add_reaction` | function | def add_reaction(repo: str, comment_id: int, content: str = \"eyes\") -> None |\n| `ensure_branch` | function | def ensure_branch(repo: str, branch: str) -> None |\n| `put_file` | function | def put_file(repo: str, branch: str, path: str, content: str, message: str) -> None |\n| `push_artifac",
      "score": 2.223,
      "key_symbols": [
        {
          "name": "_log",
          "kind": "variable",
          "signature": "_log = logging.getLogger(\"github_client\")",
          "docstring": "",
          "start_line": 22,
          "end_line": 22
        },
        {
          "name": "_warn_pat_over_app",
          "kind": "function",
          "signature": "def _warn_pat_over_app() -> None:",
          "docstring": "Один раз на процесс: PAT задан вместе с App и молча его отключает.\n\n    Симптом на стороне GitHub — всё постится от имени владельца токена, а не от\n    приложения, и понять это по поведению нельзя. Одиночный PAT — штатный\n    dev-фолбэк, он молчит; предупреждаем только про КОНФЛИКТ настроек.\n    Предупреждение одноразовое: _auth_headers зовётся на каждый REST-вызов.",
          "start_line": 99,
          "end_line": 115
        },
        {
          "name": "_auth_headers",
          "kind": "function",
          "signature": "def _auth_headers(repo: str) -> dict:",
          "docstring": "PAT path for the pilot: if GH_TOKEN/GITHUB_TOKEN is set, use it directly\n    (repo-agnostic) and skip the GitHub App flow. Otherwise per-repo App auth.",
          "start_line": 118,
          "end_line": 126,
          "source_excerpt": "def _auth_headers(repo: str) -> dict:\n    \"\"\"PAT path for the pilot: if GH_TOKEN/GITHUB_TOKEN is set, use it directly\n    (repo-agnostic) and skip the GitHub App flow. Otherwise per-repo App auth.\"\"\"\n    token = os.environ.get(\"GH_TOKEN\") or os.environ.get(\"GITHUB_TOKEN\")\n    if token:\n        if os.environ.get(\"GITHUB_APP_ID\"):\n            _warn_pat_over_app()\n        return {\"Authorization\": f\"Bearer {token}\", \"Accept\": \"application/vnd.github+json\"}\n    return _installation_token_headers(repo)"
        },
        {
          "name": "auth_token",
          "kind": "function",
          "signature": "def auth_token(repo: str) -> str:",
          "docstring": "Голый токен для внешних процессов (git clone, gh CLI).\n\n    Токен per-repo: под GitHub App у каждой установки своя пара, поэтому\n    репозиторий обязателен. PAT-путь всё равно вернёт один и тот же токен.",
          "start_line": 226,
          "end_line": 231,
          "source_excerpt": "def auth_token(repo: str) -> str:\n    \"\"\"Голый токен для внешних процессов (git clone, gh CLI).\n\n    Токен per-repo: под GitHub App у каждой установки своя пара, поэтому\n    репозиторий обязателен. PAT-путь всё равно вернёт один и тот же токен.\"\"\"\n    return _auth_headers(repo)[\"Authorization\"].split(\" \", 1)[1]"
        }
      ]
    },
    {
      "path": "shared/workflow_types.py",
      "title": "File: shared/workflow_types.py",
      "summary": "`shared/workflow_types.py` is a python source file in the Utility layer.",
      "snippet": "`shared/workflow_types.py` is a python source file in the Utility layer.",
      "excerpt": "# shared/workflow_types.py\n\n## Overview\n\n`shared/workflow_types.py` is a python source file in the Utility layer.\n\nIt exposes 27 public symbols.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `IssueInput` | class | class IssueInput |\n| `UserComment` | class | class UserComment |\n| `WebhookAuditInput` | class | class WebhookAuditInput |\n| `Deadlines` | class | class Deadlines |\n| `LifecycleState` | class | class LifecycleState |\n| `OrphanEventInput` | class | class OrphanEventInput |\n| `CommentAckInput` | class | class CommentAckInput |\n| `ProtocolState` | class | class ProtocolState |\n| `GateResult` | class | class GateResult |\n| `ClassificationResult` | class | class ClassificationResult |\n| `DuplicateResult` | class | class DuplicateResult |\n| `PriorityResult` | class | class PriorityResult |\n| `AnalyzeInput` | class | class AnalyzeInput |\n| `BftRequest` | class | class BftRequest |\n| `EstimateRequest` | class | class EstimateRequest |\n| `EstimationContext` | class | class EstimationContext |\n| `EstimateResult` | class | class EstimateResult |\n| `SolutionProfile` | class | class SolutionProfile |\n| `ClusterMember` | class | class ClusterMember |\n| `Cluster` | class | class Cluster |\n| `ClusterSet` | class | class ClusterSet |\n| `UnifyingIssueDraft` | class | class UnifyingIssueDraft |\n| `ConsolidationInput` | class | class ConsolidationInput |\n| `DeliveryZone` | class | class DeliveryZone |\n| `Taxonomy` | class | class Taxonomy |\n| `ZoneAssignment` | cl",
      "score": 2.008
    },
    {
      "path": "worker/activities.py",
      "title": "File: worker/activities.py",
      "summary": "Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на GitHub Actions).",
      "snippet": "Activities — вся содержательная логика, перенесённая из advisor/gate.py, classify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py (версия на GitHub Actions).",
      "excerpt": "# worker/activities.py\n\n## Overview\n\nActivities — вся содержательная логика, перенесённая из advisor/gate.py,\nclassify.py, duplicate_check.py, intake_filter.py, scripts/priority/score.py\n(версия на GitHub Actions). Изменился только транспорт: вместо чтения\nGITHUB_EVENT_PATH и вызова через subprocess-CLI-скрипт — обычные Python-\nфункции, вызываемые Temporal-воркером напрямую.\n\nIt exposes 104 public symbols and depends on 16 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `logger` | variable | logger = logging.getLogger(__name__) |\n| `PROMPTS_DIR` | constant | PROMPTS_DIR = Path(\"/app/prompts\") |\n| `CONFIG_DIR` | constant | CONFIG_DIR = Path(\"/app/config\") |\n| `WORKSPACE_DIR` | constant | WORKSPACE_DIR = Path(\"/app/workspace\") |\n| `GateExtraction` | class | class GateExtraction |\n| `ClassificationExtraction` | class | class ClassificationExtraction |\n| `DuplicateCandidate` | class | class DuplicateCandidate |\n| `DuplicateExtraction` | class | class DuplicateExtraction |\n| `PriorityExtraction` | class | class PriorityExtraction |\n| `prefilter_bot_and_security` | function | def prefilter_bot_and_security(issue: IssueInput, origin_agent: bool = False) -> str \\| None |\n| `intake_gate` | function | def intake_gate(issue: IssueInput, comment_thread: list[str]) -> GateResult |\n| `post_clarifying_question` | function | def post_clarifying_question(issue: IssueInput, questions: str) -> None |\n| `close_as_spam` | function | def close_as_spam(issue: IssueI",
      "score": 2.008
    },
    {
      "path": "worker/worker.py",
      "title": "File: worker/worker.py",
      "summary": "`worker/worker.py` is a python source file in the Application layer.",
      "snippet": "`worker/worker.py` is a python source file in the Application layer.",
      "excerpt": "# worker/worker.py\n\n## Overview\n\n`worker/worker.py` is a python source file in the Application layer.\n\nIt exposes 1 public symbol and depends on 7 other files.\n\n## Public API\n\n| Symbol | Kind | Signature |\n| --- | --- | --- |\n| `main` | function | async def main() -> None |\n\n## Depends on\n\n- `worker/activities.py`\n- `worker/consolidation_activities.py`\n- `worker/consolidation_workflow.py`\n- `shared/__init__.py`\n- `shared/sentry_setup.py`\n- `shared/temporal_client.py`\n- `worker/workflows.py`\n\n## Used by\n\nImported by 25 files in this repository.\n\n- `scripts/smoke_temporal.py`\n- `tests/test_agent_event_workflow.py`\n- `tests/test_agents_as_children.py`\n- `tests/test_awaiting_wiring.py`\n- `tests/test_bft_workflow.py`\n- `tests/test_clarify_after_analysis.py`\n- `tests/test_comment_ack.py`\n- `tests/test_develop_autostart.py`\n- `tests/test_duplicate_exit_with_existing_labels.py`\n- `tests/test_duplicate_phase_transitions.py`\n- `tests/test_e2e_issue_lifecycle.py`\n- `tests/test_fnr3_workflow.py`\n- `tests/test_followup_dialog.py`\n- `tests/test_lifecycle_loop.py`\n- `tests/test_park_deadline_absolute.py`\n- `tests/test_park_deadlines.py`\n- `tests/test_ready_for_dev.py`\n- `tests/test_research_autostart.py`\n- `tests/test_workflow_analysis.py`\n- `tests/test_workflow_batch.py`\n- `tests/test_workflow_closed_by_merge.py`\n- `tests/test_workflow_estimation.py`\n- `tests/test_workflow_issue_closed.py`\n- `tests/test_workflow_lifecycle_stage.py`\n- `tests/test_workflow_protocol.py`\n\n## Usage Notes\n\n**Lay",
      "score": 2.008
    }
  ],
  "note": "DEGRADED: no LLM provider configured (set REPOWISE_PROVIDER + API key). Synthesis is what is missing here, not retrieval. code_rationale carries rationale comments mined from the candidate source — they may already answer the question.",
  "best_guesses": [
    {
      "file": "webhook/main.py",
      "why_relevant": "Implements function github_webhook.",
      "score": 2.868
    },
    {
      "file": "worker/github_client.py",
      "why_relevant": "Обёртка над GitHub REST API.",
      "score": 2.223
    },
    {
      "file": "shared/workflow_types.py",
      "why_relevant": "`shared/workflow_types.py` is a python source file in the Utility layer..",
      "score": 2.008
    }
  ],
  "code_rationale": [
    {
      "path": "worker/github_client.py",
      "lines": [
        119,
        120
      ],
      "comment": "PAT path for the pilot: if GH_TOKEN/GITHUB_TOKEN is set, use it directly (repo-agnostic) and skip the GitHub App flow. Otherwise per-repo App auth.",
      "matched_terms": [
        "github"
      ]
    }
  ],
  "next_action_hint": "Start from webhook/main.py — it ranked highest, and best_guesses says why each candidate is in the running.",
  "_meta": {
    "timing_ms": 431.3,
    "hint": "Synthesis is what is missing here, not retrieval. retrieval_quality rates the ranked hits; start from the first one.",
    "index_age_days": 0,
    "indexed_commit": "7ba6a6d6301c",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "degraded": "no-llm-provider"
  },
  "candidates": [
    {
      "path": "webhook/main.py",
      "lines": "62-612",
      "defines": "get_temporal_client:111, verify_signature:118, verify_agent_signature:268, agent_event:312, github_webhook:384, HUMAN_DECISION_LABELS:81"
    },
    {
      "path": "worker/github_client.py",
      "lines": "22-231",
      "defines": "GitCommandError:460, post_comment:129, add_label:146, remove_label:155, create_issue:174, close_issue:193"
    },
    {
      "path": "shared/workflow_types.py",
      "defines": "IssueInput:5, UserComment:16, WebhookAuditInput:33, Deadlines:49, LifecycleState:110, OrphanEventInput:151"
    },
    {
      "path": "worker/activities.py",
      "defines": "GateExtraction:79, ClassificationExtraction:84, DuplicateCandidate:89, DuplicateExtraction:95, PriorityExtraction:99, FollowupExtraction:581"
    },
    {
      "path": "worker/worker.py",
      "defines": "main:34"
    }
  ]
}

## Ход 4 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "webhook/main.py::verify_signature"
}
```

**Ответ:**

{
  "symbol_id": "webhook/main.py::verify_signature",
  "file": "webhook/main.py",
  "name": "verify_signature",
  "kind": "function",
  "qualified_name": "webhook.main.verify_signature",
  "signature": "def verify_signature(body: bytes, signature_header: str | None) -> None",
  "language": "python",
  "start_line": 118,
  "end_line": 124,
  "symbol_start_line": 118,
  "symbol_end_line": 124,
  "source": "   118\tdef verify_signature(body: bytes, signature_header: str | None) -> None:\n   119\t    secret = os.environ[\"GITHUB_WEBHOOK_SECRET\"].encode()\n   120\t    if not signature_header or not signature_header.startswith(\"sha256=\"):\n   121\t        raise HTTPException(status_code=401, detail=\"Missing signature\")\n   122\t    expected = \"sha256=\" + hmac.new(secret, body, hashlib.sha256).hexdigest()\n   123\t    if not hmac.compare_digest(expected, signature_header):\n   124\t        raise HTTPException(status_code=401, detail=\"Invalid signature\")",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 11.93,
    "index_age_days": 0,
    "indexed_commit": "7ba6a6d6301c",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 6855
  }
}

## Ход 5 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "payload[...][\"user\"][\"type\"]",
  "mode": "path"
}
```

**Ответ:**

{
  "results": [],
  "mode": "path",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "7ba6a6d6301c",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 6 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "bootstrap_labels",
  "mode": "path"
}
```

**Ответ:**

{
  "results": [],
  "mode": "path",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "7ba6a6d6301c",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "grep_hint": "No indexed match for identifier 'bootstrap_labels'. Retry with mode=\"symbol\" (or check spelling/casing); if you need every literal usage for an exhaustive sweep such as a rename, Grep is the right tool for that."
}

## Ход 7 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "test_github_client",
  "mode": "path"
}
```

**Ответ:**

{
  "results": [],
  "mode": "path",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "7ba6a6d6301c",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "grep_hint": "No indexed match for identifier 'test_github_client'. Retry with mode=\"symbol\" (or check spelling/casing); if you need every literal usage for an exhaustive sweep such as a rename, Grep is the right tool for that."
}

## Ход 8 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "scripts/bootstrap_labels",
  "mode": "symbol"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": ".claude/skills/brainstorming/scripts/server.cjs::bootstrapPage",
      "name": "bootstrapPage",
      "kind": "function",
      "file": ".claude/skills/brainstorming/scripts/server.cjs",
      "start_line": 188,
      "end_line": 200,
      "signature": "function bootstrapPage(key)",
      "qualified_name": ".claude.skills.brainstorming.scripts.server.bootstrapPage",
      "language": "javascript",
      "score": 20.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "scripts/demo_e2e.py::STOP_LABELS",
      "name": "STOP_LABELS",
      "kind": "constant",
      "file": "scripts/demo_e2e.py",
      "start_line": 57,
      "end_line": 58,
      "signature": "STOP_LABELS = (\"phase:failed\", \"failed:analyze\", \"needs-human:triage\",",
      "qualified_name": "scripts.demo_e2e.STOP_LABELS",
      "language": "python",
      "score": 20.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "scripts/diag.py::build_report",
      "name": "build_report",
      "kind": "function",
      "file": "scripts/diag.py",
      "start_line": 146,
      "end_line": 167,
      "signature": "def build_report(repo: str | None) -> tuple[list[str], bool]",
      "qualified_name": "scripts.diag.build_report",
      "language": "python",
      "score": 10.1,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "scripts/diag.py::_is_set",
      "name": "_is_set",
      "kind": "function",
      "file": "scripts/diag.py",
      "start_line": 43,
      "end_line": 44,
      "signature": "def _is_set(name: str) -> bool",
      "qualified_name": "scripts.diag._is_set",
      "language": "python",
      "score": 10.09,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "scripts/e2e_live.py::main",
      "name": "main",
      "kind": "function",
      "file": "scripts/e2e_live.py",
      "start_line": 183,
      "end_line": 244,
      "signature": "async def main(argv: list[str] | None = None) -> int",
      "qualified_name": "scripts.e2e_live.main",
      "language": "python",
      "score": 10.07,
      "next": "get_symbol"
    }
  ],
  "mode": "symbol",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "7ba6a6d6301c",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "candidates": [
    {
      "path": ".claude/skills/brainstorming/scripts/server.cjs"
    },
    {
      "path": "scripts/demo_e2e.py"
    },
    {
      "path": "scripts/diag.py"
    },
    {
      "path": "scripts/e2e_live.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches 'scripts/bootstrap_labels'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}

## Ход 9 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "ensure_labels_exist",
  "mode": "symbol"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "worker/activities.py::finish_command_labels",
      "name": "finish_command_labels",
      "kind": "function",
      "file": "worker/activities.py",
      "start_line": 499,
      "end_line": 523,
      "signature": "async def finish_command_labels(repo: str, issue_number: int, command: str, ok: bool) -> None",
      "qualified_name": "worker.activities.finish_command_labels",
      "language": "python",
      "score": 10.06,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::_finish_labels",
      "name": "_finish_labels",
      "kind": "function",
      "file": "worker/workflows.py",
      "start_line": 230,
      "end_line": 242,
      "signature": "async def _finish_labels(repo: str, issue_number: int, command: str, ok: bool) -> None",
      "qualified_name": "worker.workflows._finish_labels",
      "language": "python",
      "score": 10.04,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/commands.py::running_labels",
      "name": "running_labels",
      "kind": "function",
      "file": "shared/commands.py",
      "start_line": 55,
      "end_line": 57,
      "signature": "def running_labels(command: str) -> tuple[str, ...]",
      "qualified_name": "shared.commands.running_labels",
      "language": "python",
      "score": 10.03,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/labels.py::parse_root_issue",
      "name": "parse_root_issue",
      "kind": "function",
      "file": "shared/labels.py",
      "start_line": 49,
      "end_line": 58,
      "signature": "def parse_root_issue(body: str | None) -> int | None",
      "qualified_name": "shared.labels.parse_root_issue",
      "language": "python",
      "score": 10.02,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/github_client.py::ensure_branch",
      "name": "ensure_branch",
      "kind": "function",
      "file": "worker/github_client.py",
      "start_line": 245,
      "end_line": 269,
      "signature": "def ensure_branch(repo: str, branch: str) -> None",
      "qualified_name": "worker.github_client.ensure_branch",
      "language": "python",
      "score": 10.02,
      "next": "get_symbol"
    }
  ],
  "mode": "symbol",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "7ba6a6d6301c",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "candidates": [
    {
      "path": "worker/activities.py"
    },
    {
      "path": "worker/workflows.py"
    },
    {
      "path": "shared/commands.py"
    },
    {
      "path": "shared/labels.py"
    },
    {
      "path": "worker/github_client.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches 'ensure_labels_exist'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}

## Ход 10 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "github_client.*label",
  "mode": "symbol"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "worker/github_client.py::add_label",
      "name": "add_label",
      "kind": "function",
      "file": "worker/github_client.py",
      "start_line": 146,
      "end_line": 152,
      "signature": "def add_label(repo: str, issue_number: int, label: str) -> None",
      "qualified_name": "worker.github_client.add_label",
      "language": "python",
      "score": 50.13,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/github_client.py::remove_label",
      "name": "remove_label",
      "kind": "function",
      "file": "worker/github_client.py",
      "start_line": 155,
      "end_line": 171,
      "signature": "def remove_label(repo: str, issue_number: int, label: str) -> None",
      "qualified_name": "worker.github_client.remove_label",
      "language": "python",
      "score": 50.03,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_github_client_labels.py::test_label_name_is_url_encoded",
      "name": "test_label_name_is_url_encoded",
      "kind": "function",
      "file": "tests/test_github_client_labels.py",
      "start_line": 26,
      "end_line": 43,
      "signature": "def test_label_name_is_url_encoded(monkeypatch)",
      "qualified_name": "tests.test_github_client_labels.test_label_name_is_url_encoded",
      "language": "python",
      "score": 45.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_github_client_labels.py::test_missing_label_is_not_an_error",
      "name": "test_missing_label_is_not_an_error",
      "kind": "function",
      "file": "tests/test_github_client_labels.py",
      "start_line": 46,
      "end_line": 58,
      "signature": "def test_missing_label_is_not_an_error(monkeypatch)",
      "qualified_name": "tests.test_github_client_labels.test_missing_label_is_not_an_error",
      "language": "python",
      "score": 45.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/github_client.py::_auth_headers",
      "name": "_auth_headers",
      "kind": "function",
      "file": "worker/github_client.py",
      "start_line": 118,
      "end_line": 126,
      "signature": "def _auth_headers(repo: str) -> dict",
      "qualified_name": "worker.github_client._auth_headers",
      "language": "python",
      "score": 20.56,
      "next": "get_symbol"
    }
  ],
  "mode": "symbol",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "7ba6a6d6301c",
    "live_head": "230d40231d62",
    "index_behind": true,
    "stale_warning": "A file this response serves changed after indexing — verify against source or run `repowise update`.",
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "candidates": [
    {
      "path": "worker/github_client.py"
    },
    {
      "path": "tests/test_github_client_labels.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches 'github_client.*label'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}
