---
session: rw-openhands-po-helper-org__poh-issue-agents-64
workspace: contour
turns: 16
started: 2026-08-22T19:50:21Z
finished: 2026-08-22T19:53:44Z
---

# Свежесть индекса

| репозиторий | SHA | возраст индекса |
|---|---|---|
| `poh-bft-writer` | `c7fe9bd7d1b2` | 28 мин |
| `poh-cortex` | `3c3e1a3a9e83` | 28 мин |
| `poh-helper` | `18512c1e7ce9` | 28 мин |
| `poh-infra` | `a1db4f02f10c` | 28 мин |
| `poh-issue-agents` | `993d8561f100` | 28 мин |
| `poh-memory-engine` | `194e39319b3f` | 28 мин |
| `poh-pr-agents` | `9f15ada9e4e9` | 28 мин |
| `poh-scheduller` | `04cc3f47aff9` | 28 мин |
| `poh-sprint-agents` | `c41cb5b2ce18` | 28 мин |
| `poh-demo-checkout` | `2e7c62aa955e` | 2 сут |

# Диалог

## Ход 1 · `get_overview` · contour

**Запрос:**

```json
{
  "repo": "default"
}
```

**Ответ:**

{
  "error": "Unknown repo 'default'. Available: ['poh-bft-writer', 'poh-cortex', 'poh-helper', 'poh-infra', 'poh-issue-agents', 'poh-memory-engine', 'poh-pr-agents', 'poh-scheduller', 'poh-sprint-agents']",
  "remedy": "Call list_repos to see the valid repo aliases, or omit the 'repo' argument to use the default repository."
}

## Ход 2 · `get_overview` · contour

**Запрос:**

```json
{}
```

**Ответ:**

{
  "title": "Repository Overview: poh-issue-agents",
  "content_md": "# Repository Overview: poh-issue-agents\n\n**Files:** 323 | **Lines:** 80733 | **Import cycles:** 1",
  "code_health": {
    "average_health": 8.32,
    "band": "healthy",
    "hotspot_health": 5.1,
    "worst_performer_path": "worker/workflows.py",
    "worst_performer_score": 1.0,
    "open_findings": 520,
    "file_count": 371,
    "distribution": {
      "total_files": 371,
      "total_nloc": 54856,
      "bands": {
        "healthy": {
          "files": 334,
          "nloc": 41367,
          "pct": 75.4
        },
        "warning": {
          "files": 33,
          "nloc": 7738,
          "pct": 14.1
        },
        "alert": {
          "files": 4,
          "nloc": 5751,
          "pct": 10.5
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
    "files_git_attributed": 374,
    "hotspot_count": 46,
    "avg_bus_factor": 0.7,
    "files_with_bus_factor_1": 124,
    "churn_trend": "increasing",
    "top_churn_modules": [
      ".claude/skills",
      "worker/activities.py",
      "worker/workflows.py",
      "worker/worker.py",
      "README.md"
    ]
  },
  "knowledge_map": {
    "top_owners": [
      {
        "name": "kibarik",
        "files_owned": 97,
        "percentage": 25.9
      },
      {
        "name": "kibarik",
        "files_owned": 71,
        "percentage": 19.0
      },
      {
        "name": "openhands-agent",
        "files_owned": 6,
        "percentage": 1.6
      }
    ]
  },
  "community_summary": [
    {
      "id": 0,
      "label": "tests",
      "size": 11
    },
    {
      "id": 1,
      "label": "tests (27)",
      "size": 11
    },
    {
      "id": 2,
      "label": "server",
      "size": 7
    },
    {
      "id": 3,
      "label": "tests (43)",
      "size": 7
    },
    {
      "id": 4,
      "label": "worker",
      "size": 5
    },
    {
      "id": 5,
      "label": "external:~/threads",
      "size": 3
    },
    {
      "id": 6,
      "label": "tests (6)",
      "size": 3
    },
    {
      "id": 7,
      "label": "claude",
      "size": 1
    },
    {
      "id": 8,
      "label": "installed_skills",
      "size": 1
    },
    {
      "id": 9,
      "label": "commands",
      "size": 1
    }
  ],
  "content_hint": "Overview essay trimmed to its summary section. Call get_overview(include=[\"content\"]) for the full walkthrough.",
  "outline": {
    "root": {
      "page_id": "repo_overview:poh-issue-agents",
      "title": "Repository Overview: poh-issue-agents"
    },
    "total_pages": 269,
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
        "descendants": 9
      },
      {
        "section": "6",
        "page_id": "module_page:shared",
        "title": "Utility Shared",
        "page_type": "module_page",
        "target_path": "shared",
        "descendants": 49
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
        "descendants": 112
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
        "page_id": "symbol_spotlight:tests/conftest.py::forge_env",
        "title": "Symbol: tests.conftest.forge_env",
        "page_type": "symbol_spotlight",
        "target_path": "tests/conftest.py::forge_env"
      },
      {
        "section": "22",
        "page_id": "symbol_spotlight:tests/conftest.py::make_fake_set_labels",
        "title": "Symbol: tests.conftest.make_fake_set_labels",
        "page_type": "symbol_spotlight",
        "target_path": "tests/conftest.py::make_fake_set_labels"
      },
      {
        "section": "23",
        "page_id": "symbol_spotlight:tests/conftest.py::rules",
        "title": "Symbol: tests.conftest.rules",
        "page_type": "symbol_spotlight",
        "target_path": "tests/conftest.py::rules"
      },
      {
        "section": "24",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::FakeGitHub",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::FakeGitHub"
      },
      {
        "section": "25",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::__init__",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.__init__",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::__init__"
      },
      {
        "section": "26",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::add_label",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.add_label",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::add_label"
      },
      {
        "section": "27",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::add_reaction",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.add_reaction",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::add_reaction"
      },
      {
        "section": "28",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::branch_exists",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.branch_exists",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::branch_exists"
      },
      {
        "section": "29",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::comment",
        "title": "Symbol: tests.test_estimate_activities.comment",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::comment"
      },
      {
        "section": "30",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::fake",
        "title": "Symbol: tests.test_estimate_activities.fake",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::fake"
      },
      {
        "section": "31",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::get_file",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.get_file",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::get_file"
      },
      {
        "section": "32",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::get_issue",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.get_issue",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::get_issue"
      },
      {
        "section": "33",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::list_comments",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.list_comments",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::list_comments"
      },
      {
        "section": "34",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::post_comment",
        "title": "Symbol: tests.test_estimate_activities.FakeGitHub.post_comment",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::post_comment"
      },
      {
        "section": "35",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_ack_puts_eyes_on_the_command_comment",
        "title": "Symbol: tests.test_estimate_activities.test_ack_puts_eyes_on_the_command_comment",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_ack_puts_eyes_on_the_command_comment"
      },
      {
        "section": "36",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_bot_comments_and_commands_are_excluded_from_the_thread",
        "title": "Symbol: tests.test_estimate_activities.test_bot_comments_and_commands_are_excluded_from_the_thread",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_bot_comments_and_commands_are_excluded_from_the_thread"
      },
      {
        "section": "37",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_bug_branch_is_used_when_there_is_no_research_branch",
        "title": "Symbol: tests.test_estimate_activities.test_bug_branch_is_used_when_there_is_no_research_branch",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_bug_branch_is_used_when_there_is_no_research_branch"
      },
      {
        "section": "38",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_compute_activity_returns_rendered_markdown",
        "title": "Symbol: tests.test_estimate_activities.test_compute_activity_returns_rendered_markdown",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_compute_activity_returns_rendered_markdown"
      },
      {
        "section": "39",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_context_carries_title_body_and_labels",
        "title": "Symbol: tests.test_estimate_activities.test_context_carries_title_body_and_labels",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_context_carries_title_body_and_labels"
      },
      {
        "section": "40",
        "page_id": "symbol_spotlight:tests/test_estimate_activities.py::test_error_reports_the_stage_and_reacts",
        "title": "Symbol: tests.test_estimate_activities.test_error_reports_the_stage_and_reacts",
        "page_type": "symbol_spotlight",
        "target_path": "tests/test_estimate_activities.py::test_error_reports_the_stage_and_reacts"
      }
    ],
    "sections_total": 91,
    "sections_truncated": true
  },
  "outline_hint": "The stored page tree — the same outline the web app and the editor extension render. Every 'section' in this response indexes into it, and 'descendants' is how much sits below an entry. Top rung only by default; call get_overview(include=[\"outline\"]) for one level deeper, then get_context on an entry's target_path to read it.",
  "architecture": {
    "layers": [
      {
        "name": "Application",
        "description": "",
        "file_count": 57
      },
      {
        "name": "Config",
        "description": "",
        "file_count": 139
      },
      {
        "name": "Utility",
        "description": "",
        "file_count": 21
      },
      {
        "name": "Docs & Tooling",
        "description": "",
        "file_count": 43
      },
      {
        "name": "Test",
        "description": "",
        "file_count": 111
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
      "section": "6.20"
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
    "indexed_commit": "8ee2a0cd85f8",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "omitted": {
      "refs": [
        "87a528171e88"
      ],
      "tokens": 2044,
      "restore": "Run `repowise expand <ref>` from the repo, or call get_symbol(\"repowise#<ref>\", query=...) to retrieve the omitted content."
    }
  },
  "omission_marker": "[repowise#87a528171e88: 55 lines omitted (~2044 tokens); restore: repowise expand 87a528171e88]"
}

## Ход 3 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "classify_issue classification advisor:feature-request advisor:bug",
  "mode": "hybrid"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "worker/activities.py::classify_issue",
      "name": "classify_issue",
      "kind": "function",
      "file": "worker/activities.py",
      "start_line": 538,
      "end_line": 576,
      "signature": "def classify_issue(issue: IssueInput, bft_on_triage: bool = False) -> ClassificationResult",
      "qualified_name": "worker.activities.classify_issue",
      "language": "python",
      "score": 160.0,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_agents_as_children.py::ISSUE",
      "name": "ISSUE",
      "kind": "constant",
      "file": "tests/test_agents_as_children.py",
      "start_line": 35,
      "end_line": 35,
      "signature": "ISSUE = 7",
      "qualified_name": "tests.test_agents_as_children.ISSUE",
      "language": "python",
      "score": 50.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_bft_workflow.py::ISSUE",
      "name": "ISSUE",
      "kind": "constant",
      "file": "tests/test_bft_workflow.py",
      "start_line": 31,
      "end_line": 31,
      "signature": "ISSUE = 7",
      "qualified_name": "tests.test_bft_workflow.ISSUE",
      "language": "python",
      "score": 50.01,
      "next": "get_symbol"
    },
    {
      "title": "Symbol: worker.activities.classify_issue",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.classify_issue\n\n**Kind:** function | **Defined in:** `worker/activities.py` | **Estimated complexity:** 4\n\n```\ndef classify_issue(issue: IssueInput, bft_on_triage: bool = False) ->",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::classify_issue",
      "file": "worker/activities.py",
      "type": "page"
    },
    {
      "title": "Symbol: shared.workflow_types.ClassificationResult",
      "page_type": "symbol_spotlight",
      "snippet": "# shared.workflow_types.ClassificationResult\n\n**Kind:** class | **Defined in:** `shared/workflow_types.py` | **Estimated complexity:** 1\n\n```\nclass ClassificationResult\n```\n\n## Overview\n\n`Classificati",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "shared/workflow_types.py::ClassificationResult",
      "file": "shared/workflow_types.py",
      "type": "page"
    }
  ],
  "mode": "hybrid",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "8ee2a0cd85f8",
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
      "path": "tests/test_agents_as_children.py"
    },
    {
      "path": "tests/test_bft_workflow.py"
    },
    {
      "path": "shared/workflow_types.py"
    }
  ],
  "exact_match": true
}

## Ход 4 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/activities.py::classify_issue"
}
```

**Ответ:**

{
  "symbol_id": "worker/activities.py::classify_issue",
  "file": "worker/activities.py",
  "name": "classify_issue",
  "kind": "function",
  "qualified_name": "worker.activities.classify_issue",
  "signature": "def classify_issue(issue: IssueInput, bft_on_triage: bool = False) -> ClassificationResult",
  "language": "python",
  "start_line": 538,
  "end_line": 576,
  "symbol_start_line": 538,
  "symbol_end_line": 576,
  "source": "   538\tdef classify_issue(issue: IssueInput, bft_on_triage: bool = False) -> ClassificationResult:\n   539\t    \"\"\"Тип запроса плюс ответ advisor комментарием.\n   540\t\n   541\t    `bft_on_triage=True` глушит публикацию ответа РОВНО для запроса функционала:\n   542\t    на него отвечает БФТ, и два комментария подряд означали бы, что первый\n   543\t    неактуален уже в момент публикации. Для бага, консультации и «уже\n   544\t    реализовано» ответ публикуется как прежде — БФТ по ним не собирается, и\n   545\t    молчание оставило бы Issue вообще без содержательного комментария.\n   546\t\n   547\t    Решение принимается ЗДЕСЬ, а не отдельной активностью публикации, потому что\n   548\t    зависит от категории — а категорию знает только эта активность. Развести их\n   549\t    значило бы гонять текст ответа через воркфлоу ради условия, которое здесь\n   550\t    уже вычислено.\n   551\t\n   552\t    Аргумент со значением по умолчанию, а не новая activity: прогоны прежнего\n   553\t    поколения зовут её одним аргументом и обязаны получить прежнее поведение.\n   554\t    \"\"\"\n   555\t    capabilities = (WORKSPACE_DIR / \"capabilities.md\").read_text(encoding=\"utf-8\") \\\n   556\t        if (WORKSPACE_DIR / \"capabilities.md\").exists() else \"(пусто)\"\n   557\t    user_message = f\"Заголовок: {issue.title}\\n\\nОписание:\\n{issue.body}\\n\\nИзвестный функционал:\\n{capabilities}\"\n   558\t    result = llm.extract(\n   559\t        _load_prompt(\"system_advisor.md\"), user_message, ClassificationExtraction, model=llm.MODEL_CLASSIFY,\n   560\t    )\n   561\t    label_map = {\n   562\t        \"EXISTING\": \"advisor:existing-functionality\",\n   563\t        \"CONSULTATION\": \"advisor:consultation\",\n   564\t        \"BUG\": \"advisor:bug\",\n   565\t        \"FEATURE\": \"advisor:feature-request\",\n   566\t    }\n   567\t    label = label_map.get(result.category, \"advisor:answered\")\n   568\t    # The advisor prompt still asks the model to prefix its answer with a\n   569\t    # legacy [[MARKER]] (from the pre-Instructor text-parsing era). The\n   570\t    # category is now carried structurally, so strip that marker line before\n   571\t    # posting — it must not appear in the user-facing comment.\n   572\t    answer = re.sub(r\"^\\s*\\[\\[[^\\]]+\\]\\]\\s*\", \"\", result.answer)\n   573\t    if not (bft_on_triage and label == \"advisor:feature-request\"):\n   574\t        github_client.post_comment(issue.repo, issue.issue_number, answer)\n   575\t    github_client.add_label(issue.repo, issue.issue_number, label)\n   576\t    return ClassificationResult(label=label, answer=answer)",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 15.97,
    "index_age_days": 0,
    "indexed_commit": "8ee2a0cd85f8",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 38622
  }
}

## Ход 5 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "shared/workflow_types.py::ClassificationResult"
}
```

**Ответ:**

{
  "symbol_id": "shared/workflow_types.py::ClassificationResult",
  "file": "shared/workflow_types.py",
  "name": "ClassificationResult",
  "kind": "class",
  "qualified_name": "shared.workflow_types.ClassificationResult",
  "signature": "class ClassificationResult",
  "language": "python",
  "start_line": 209,
  "end_line": 211,
  "symbol_start_line": 209,
  "symbol_end_line": 211,
  "source": "   209\tclass ClassificationResult:\n   210\t    label: str  # \"advisor:existing-functionality\" | \"advisor:consultation\" | \"advisor:bug\" | \"advisor:feature-request\"\n   211\t    answer: str",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 9.85,
    "index_age_days": 0,
    "indexed_commit": "8ee2a0cd85f8",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 3481
  }
}

## Ход 6 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "ClassificationExtraction EXISTING CONSULTATION BUG FEATURE",
  "mode": "hybrid"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "worker/activities.py::ClassificationExtraction",
      "name": "ClassificationExtraction",
      "kind": "class",
      "file": "worker/activities.py",
      "start_line": 86,
      "end_line": 88,
      "signature": "class ClassificationExtraction",
      "qualified_name": "worker.activities.ClassificationExtraction",
      "language": "python",
      "score": 160.0,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/workflow_types.py::ClassificationResult",
      "name": "ClassificationResult",
      "kind": "class",
      "file": "shared/workflow_types.py",
      "start_line": 209,
      "end_line": 211,
      "signature": "class ClassificationResult",
      "qualified_name": "shared.workflow_types.ClassificationResult",
      "language": "python",
      "score": 15.24,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/consolidation_activities.py::AssignExtraction",
      "name": "AssignExtraction",
      "kind": "class",
      "file": "worker/consolidation_activities.py",
      "start_line": 136,
      "end_line": 138,
      "signature": "class AssignExtraction",
      "qualified_name": "worker.consolidation_activities.AssignExtraction",
      "language": "python",
      "score": 15.02,
      "next": "get_symbol"
    },
    {
      "title": "Symbol: worker.activities.ClassificationExtraction",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.ClassificationExtraction\n\n**Kind:** class | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\nclass ClassificationExtraction\n```\n\n## Overview\n\n`Classificati",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::ClassificationExtraction",
      "file": "worker/activities.py",
      "type": "page"
    },
    {
      "title": "Symbol: worker.activities.classify_issue",
      "page_type": "symbol_spotlight",
      "snippet": "`tests/test_develop_child.py`\n- `tests/test_develop_followups.py`\n- `tests/test_duplicate_exit_with_existing_labels.py`\n- `tests/test_e2e_issue_lifecycle.py`\n- `tests/test_estimate_activities.py`\n- `t",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::classify_issue",
      "file": "worker/activities.py",
      "type": "page"
    }
  ],
  "mode": "hybrid",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "8ee2a0cd85f8",
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
      "path": "shared/workflow_types.py"
    },
    {
      "path": "worker/consolidation_activities.py"
    }
  ],
  "exact_match": true
}

## Ход 7 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/activities.py::ClassificationExtraction"
}
```

**Ответ:**

{
  "symbol_id": "worker/activities.py::ClassificationExtraction",
  "file": "worker/activities.py",
  "name": "ClassificationExtraction",
  "kind": "class",
  "qualified_name": "worker.activities.ClassificationExtraction",
  "signature": "class ClassificationExtraction",
  "language": "python",
  "start_line": 86,
  "end_line": 88,
  "symbol_start_line": 86,
  "symbol_end_line": 88,
  "source": "    86\tclass ClassificationExtraction(BaseModel):\n    87\t    category: str = Field(description=\"EXISTING | CONSULTATION | BUG | FEATURE\")\n    88\t    answer: str",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 15.46,
    "index_age_days": 0,
    "indexed_commit": "8ee2a0cd85f8",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 38622
  }
}

## Ход 8 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "analyze_requested signal analyze command workflow",
  "mode": "hybrid"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::IssueLifecycle::analyze_requested",
      "name": "analyze_requested",
      "kind": "method",
      "file": "worker/workflows.py",
      "start_line": 514,
      "end_line": 568,
      "signature": "async def analyze_requested(self, comment_id: int | None) -> None",
      "qualified_name": "worker.workflows.IssueLifecycle.analyze_requested",
      "language": "python",
      "score": 160.0,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/commands.py::ANALYZE",
      "name": "ANALYZE",
      "kind": "constant",
      "file": "shared/commands.py",
      "start_line": 20,
      "end_line": 20,
      "signature": "ANALYZE = \"analyze\"",
      "qualified_name": "shared.commands.ANALYZE",
      "language": "python",
      "score": 55.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_workflow_batch.py::test_analyze_requested_in_the_first_activation_is_not_lost",
      "name": "test_analyze_requested_in_the_first_activation_is_not_lost",
      "kind": "function",
      "file": "tests/test_workflow_batch.py",
      "start_line": 296,
      "end_line": 322,
      "signature": "async def test_analyze_requested_in_the_first_activation_is_not_lost()",
      "qualified_name": "tests.test_workflow_batch.test_analyze_requested_in_the_first_activation_is_not_lost",
      "language": "python",
      "score": 55.01,
      "next": "get_symbol"
    },
    {
      "title": "Symbol: worker.workflows.IssueLifecycle.analyze_requested",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.workflows.IssueLifecycle.analyze_requested\n\n**Kind:** method (async) | **Defined in:** `worker/workflows.py` | **Estimated complexity:** 5\n\n```\nasync def analyze_requested(self, comment_id: i",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "worker/workflows.py::analyze_requested",
      "file": "worker/workflows.py",
      "type": "page"
    },
    {
      "title": "File: shared/agent_launcher.py",
      "page_type": "file_page",
      "snippet": "е решение\n«child или root» разъедется по трём местам ровно так же, как когда-то разъехались\nформаты workflow id (см. `shared/workflow_ids.py`).\n\nКак принимается решение\n-----------------------\nНе «опи",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "shared/agent_launcher.py",
      "type": "page"
    }
  ],
  "mode": "hybrid",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "8ee2a0cd85f8",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "candidates": [
    {
      "path": "worker/workflows.py"
    },
    {
      "path": "shared/commands.py"
    },
    {
      "path": "tests/test_workflow_batch.py"
    },
    {
      "path": "shared/agent_launcher.py"
    }
  ],
  "exact_match": true
}

## Ход 9 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/workflows.py::IssueLifecycle::analyze_requested"
}
```

**Ответ:**

{
  "symbol_id": "worker/workflows.py::IssueLifecycle::analyze_requested",
  "file": "worker/workflows.py",
  "name": "analyze_requested",
  "kind": "method",
  "qualified_name": "worker.workflows.IssueLifecycle.analyze_requested",
  "signature": "async def analyze_requested(self, comment_id: int | None) -> None",
  "language": "python",
  "start_line": 514,
  "end_line": 568,
  "symbol_start_line": 514,
  "symbol_end_line": 568,
  "source": "   514\t    async def analyze_requested(self, comment_id: int | None) -> None:\n   515\t        \"\"\"По Issue запрошена аналитика — командой `/analyze` или меткой.\n   516\t\n   517\t        Цикл ведёт её сам: запрос уходит в общую очередь сигналов, а\n   518\t        обработчик фазы поднимает `IssueAnalysis` дочерним прогоном (#37).\n   519\t        Раньше здесь вешалась только метка, а работу нёс независимый воркфлоу\n   520\t        из вебхука — связь между циклом Issue и работой агента была\n   521\t        декоративной, о чём и говорил прежний докстринг.\n   522\t\n   523\t        Тяжёлую работу из самого хендлера не запускаем: run() обычно\n   524\t        припаркован в `_wait_for_signal()`, и спавн отсюда гонялся бы с\n   525\t        основным циклом за фазу. Очередь снимает гонку — решение принимает та\n   526\t        фаза, в которой Issue находится сейчас.\n   527\t\n   528\t        Сигнал может прийти в самой первой активации воркфлоу — раньше, чем\n   529\t        run() выполнил `self._issue = issue` (Temporal применяет сигналы до\n   530\t        создания задачи run()); поэтому ЖДЁМ инициализацию через\n   531\t        wait_condition, а не теряем запрос молча по `self._issue is None`.\n   532\t        \"\"\"\n   533\t        # Тот же маркер, что разводит поколения в run(): цикл и дочерние\n   534\t        # агенты приехали вместе, и прогон, не знающий одного, не знает и\n   535\t        # другого. Прежнее поколение обязано доиграть ПРЕЖНИМ кодом хендлера —\n   536\t        # иначе реплей его истории упрётся в несовпадение команд.\n   537\t        if not workflow.patched(\"issue-lifecycle-phase-loop\"):\n   538\t            if self._analyze_labeled:\n   539\t                return\n   540\t            self._analyze_labeled = True\n   541\t            await workflow.wait_condition(lambda: self._issue is not None)\n   542\t            await workflow.execute_activity(\n   543\t                activities.mark_analyzing,\n   544\t                args=[self._issue.repo, self._issue.issue_number],\n   545\t                start_to_close_timeout=timedelta(seconds=30),\n   546\t                retry_policy=RetryPolicy(maximum_attempts=3),\n   547\t            )\n   548\t            return\n   549\t\n   550\t        # Запрос уже в очереди — второй прогон был бы шумом и деньгами:\n   551\t        # повторная команда и дубль webhook-доставки означают одно намерение.\n   552\t        # Флаг ставим ДО первого await: хендлеры кооперативны (переключение\n   553\t        # только на await), поэтому почти одновременный второй сигнал увидит\n   554\t        # True. Идентификатор занятого прогона от этой гонки не спасает: к\n   555\t        # моменту второго сигнала первый может уже завершиться, и id\n   556\t        # освободится — а это законный повторный запуск, не дубль.\n   557\t        # Идущий прогон — тоже причина отказать. Пока он идёт, `ack_command`\n   558\t        # вешает на Issue метку `run:analyze`; вебхук видит `issues.labeled` и\n   559\t        # шлёт команду обратно в цикл. Своя метка возвращается как новая\n   560\t        # команда, и на живом стенде это давало три прогона подряд по одному\n   561\t        # Issue. Идентификатор занятого прогона от этого не спасает: к моменту\n   562\t        # разбора очереди первый прогон уже завершён, и id свободен.\n   563\t        if self._analyze_pending or self._analysis_running:\n   564\t            return\n   565\t        self._analyze_pending = True\n   566\t        self._analyze_comment_id = comment_id\n   567\t        await workflow.wait_condition(lambda: self._issue is not None)\n   568\t        await self._signal_queue.put(AGENT_ANALYZE)",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 20.18,
    "index_age_days": 0,
    "indexed_commit": "8ee2a0cd85f8",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 32935
  }
}

## Ход 10 · `get_context` · contour

**Запрос:**

```json
{
  "targets": [
    "shared/workflow_types.py"
  ]
}
```

**Ответ:**

{
  "targets": {
    "shared/workflow_types.py": {
      "target": "shared/workflow_types.py",
      "type": "file",
      "parent_page": {
        "title": "Utility Shared",
        "target_path": "shared",
        "section": "6"
      },
      "docs": {
        "title": "File: shared/workflow_types.py",
        "summary": "`shared/workflow_types.py` is a python source file in the Utility layer.",
        "symbols": [
          {
            "name": "IssueInput",
            "kind": "class",
            "signature": "class IssueInput",
            "line": 6,
            "symbol_id": "shared/workflow_types.py::IssueInput"
          },
          {
            "name": "WebhookAuditInput",
            "kind": "class",
            "signature": "class WebhookAuditInput",
            "line": 34,
            "symbol_id": "shared/workflow_types.py::WebhookAuditInput"
          },
          {
            "name": "Deadlines",
            "kind": "class",
            "signature": "class Deadlines",
            "line": 50,
            "symbol_id": "shared/workflow_types.py::Deadlines"
          },
          {
            "name": "LifecycleState",
            "kind": "class",
            "signature": "class LifecycleState",
            "line": 111,
            "symbol_id": "shared/workflow_types.py::LifecycleState"
          },
          {
            "name": "OrphanEventInput",
            "kind": "class",
            "signature": "class OrphanEventInput",
            "line": 157,
            "symbol_id": "shared/workflow_types.py::OrphanEventInput"
          },
          {
            "name": "CommentAckInput",
            "kind": "class",
            "signature": "class CommentAckInput",
            "line": 175,
            "symbol_id": "shared/workflow_types.py::CommentAckInput"
          },
          {
            "name": "ProtocolState",
            "kind": "class",
            "signature": "class ProtocolState",
            "line": 188,
            "symbol_id": "shared/workflow_types.py::ProtocolState"
          },
          {
            "name": "GateResult",
            "kind": "class",
            "signature": "class GateResult",
            "line": 203,
            "symbol_id": "shared/workflow_types.py::GateResult"
          },
          {
            "name": "ClassificationResult",
            "kind": "class",
            "signature": "class ClassificationResult",
            "line": 209,
            "symbol_id": "shared/workflow_types.py::ClassificationResult"
          },
          {
            "name": "DuplicateResult",
            "kind": "class",
            "signature": "class DuplicateResult",
            "line": 215,
            "symbol_id": "shared/workflow_types.py::DuplicateResult"
          },
          {
            "name": "PriorityResult",
            "kind": "class",
            "signature": "class PriorityResult",
            "line": 224,
            "symbol_id": "shared/workflow_types.py::PriorityResult"
          },
          {
            "name": "AnalyzeInput",
            "kind": "class",
            "signature": "class AnalyzeInput",
            "line": 230,
            "symbol_id": "shared/workflow_types.py::AnalyzeInput"
          },
          {
            "name": "BftRequest",
            "kind": "class",
            "signature": "class BftRequest",
            "line": 256,
            "symbol_id": "shared/workflow_types.py::BftRequest"
          },
          {
            "name": "EstimateRequest",
            "kind": "class",
            "signature": "class EstimateRequest",
            "line": 281,
            "symbol_id": "shared/workflow_types.py::EstimateRequest"
          },
          {
            "name": "EstimationContext",
            "kind": "class",
            "signature": "class EstimationContext",
            "line": 290,
            "symbol_id": "shared/workflow_types.py::EstimationContext"
          },
          {
            "name": "EstimateResult",
            "kind": "class",
            "signature": "class EstimateResult",
            "line": 301,
            "symbol_id": "shared/workflow_types.py::EstimateResult"
          },
          {
            "name": "SolutionProfile",
            "kind": "class",
            "signature": "class SolutionProfile",
            "line": 307,
            "symbol_id": "shared/workflow_types.py::SolutionProfile"
          },
          {
            "name": "ClusterMember",
            "kind": "class",
            "signature": "class ClusterMember",
            "line": 319,
            "symbol_id": "shared/workflow_types.py::ClusterMember"
          },
          {
            "name": "Cluster",
            "kind": "class",
            "signature": "class Cluster",
            "line": 326,
            "symbol_id": "shared/workflow_types.py::Cluster"
          },
          {
            "name": "ClusterSet",
            "kind": "class",
            "signature": "class ClusterSet",
            "line": 335,
            "symbol_id": "shared/workflow_types.py::ClusterSet"
          },
          {
            "name": "UnifyingIssueDraft",
            "kind": "class",
            "signature": "class UnifyingIssueDraft",
            "line": 341,
            "symbol_id": "shared/workflow_types.py::UnifyingIssueDraft"
          },
          {
            "name": "ConsolidationInput",
            "kind": "class",
            "signature": "class ConsolidationInput",
            "line": 349,
            "symbol_id": "shared/workflow_types.py::ConsolidationInput"
          },
          {
            "name": "DeliveryZone",
            "kind": "class",
            "signature": "class DeliveryZone",
            "line": 357,
            "symbol_id": "shared/workflow_types.py::DeliveryZone"
          },
          {
            "name": "Taxonomy",
            "kind": "class",
            "signature": "class Taxonomy",
            "line": 364,
            "symbol_id": "shared/workflow_types.py::Taxonomy"
          },
          {
            "name": "ZoneAssignment",
            "kind": "class",
            "signature": "class ZoneAssignment",
            "line": 369,
            "symbol_id": "shared/workflow_types.py::ZoneAssignment"
          },
          {
            "name": "Increment",
            "kind": "class",
            "signature": "class Increment",
            "line": 376,
            "symbol_id": "shared/workflow_types.py::Increment"
          },
          {
            "name": "UserComment",
            "kind": "class",
            "signature": "class UserComment",
            "line": 17,
            "symbol_id": "shared/workflow_types.py::UserComment"
          },
          {
            "name": "CommentIntent",
            "kind": "class",
            "signature": "class CommentIntent",
            "line": 383,
            "symbol_id": "shared/workflow_types.py::CommentIntent"
          },
          {
            "name": "DevelopPlan",
            "kind": "class",
            "signature": "class DevelopPlan",
            "line": 243,
            "symbol_id": "shared/workflow_types.py::DevelopPlan"
          }
        ]
      },
      "hotspot": true,
      "fix_history": {
        "fix_count": 3,
        "last_fix_days_ago": 3
      },
      "freshness": {
        "confidence_score": 1.0,
        "freshness_status": "fresh",
        "is_stale": false
      },
      "architectural_layer": {
        "name": "Utility",
        "description": "",
        "role": "edge_connector"
      },
      "episodes": 3,
      "cross_repo": {
        "co_changes_with": [
          {
            "repo": "poh-memory-engine",
            "file": "README.md",
            "strength": 0.624
          },
          {
            "repo": "poh-bft-writer",
            "file": "commands/bft-draft.md",
            "strength": 0.503
          }
        ]
      }
    }
  },
  "_meta": {
    "timing_ms": 41.32,
    "index_age_days": 0,
    "indexed_commit": "8ee2a0cd85f8",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  }
}

## Ход 11 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "test_classify_issue classification test",
  "mode": "hybrid"
}
```

**Ответ:**

{
  "results": [
    {
      "title": "Symbol: shared.workflow_types.ClassificationResult",
      "page_type": "symbol_spotlight",
      "snippet": "# shared.workflow_types.ClassificationResult\n\n**Kind:** class | **Defined in:** `shared/workflow_types.py` | **Estimated complexity:** 1\n\n```\nclass ClassificationResult\n```\n\n## Overview\n\n`Classificati",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "shared/workflow_types.py::ClassificationResult",
      "file": "shared/workflow_types.py",
      "type": "page"
    },
    {
      "title": "Symbol: worker.activities.ClassificationExtraction",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.activities.ClassificationExtraction\n\n**Kind:** class | **Defined in:** `worker/activities.py` | **Estimated complexity:** 1\n\n```\nclass ClassificationExtraction\n```\n\n## Overview\n\n`Classificati",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::ClassificationExtraction",
      "file": "worker/activities.py",
      "type": "page"
    },
    {
      "title": "Symbol: worker.activities.score_priority",
      "page_type": "symbol_spotlight",
      "snippet": ":** `worker/activities.py` | **Estimated complexity:** 7\n\n```\ndef score_priority(issue: IssueInput, classification: ClassificationResult | None,\n                   dup: DuplicateResult) -> PriorityRes",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::score_priority",
      "file": "worker/activities.py",
      "type": "page"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_agents_as_children.py::ISSUE",
      "name": "ISSUE",
      "kind": "constant",
      "file": "tests/test_agents_as_children.py",
      "start_line": 35,
      "end_line": 35,
      "signature": "ISSUE = 7",
      "qualified_name": "tests.test_agents_as_children.ISSUE",
      "language": "python",
      "score": 55.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_bft_workflow.py::ISSUE",
      "name": "ISSUE",
      "kind": "constant",
      "file": "tests/test_bft_workflow.py",
      "start_line": 31,
      "end_line": 31,
      "signature": "ISSUE = 7",
      "qualified_name": "tests.test_bft_workflow.ISSUE",
      "language": "python",
      "score": 55.01,
      "next": "get_symbol"
    }
  ],
  "mode": "hybrid",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "8ee2a0cd85f8",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "candidates": [
    {
      "path": "shared/workflow_types.py"
    },
    {
      "path": "worker/activities.py"
    },
    {
      "path": "tests/test_agents_as_children.py"
    },
    {
      "path": "tests/test_bft_workflow.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches 'test_classify_issue'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}

## Ход 12 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "IssueAnalysis workflow class",
  "mode": "hybrid"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::IssueAnalysis",
      "name": "IssueAnalysis",
      "kind": "class",
      "file": "worker/workflows.py",
      "start_line": 2393,
      "end_line": 2421,
      "signature": "class IssueAnalysis",
      "qualified_name": "worker.workflows.IssueAnalysis",
      "language": "python",
      "score": 160.0,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "worker/workflows.py::IssueAnalysis::run",
      "name": "run",
      "kind": "method",
      "file": "worker/workflows.py",
      "start_line": 2406,
      "end_line": 2421,
      "signature": "async def run(self, analyze: AnalyzeInput) -> bool",
      "qualified_name": "worker.workflows.IssueAnalysis.run",
      "language": "python",
      "score": 60.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/repowise.py::ANALYSIS",
      "name": "ANALYSIS",
      "kind": "constant",
      "file": "shared/repowise.py",
      "start_line": 32,
      "end_line": 32,
      "signature": "ANALYSIS = \"analysis\"",
      "qualified_name": "shared.repowise.ANALYSIS",
      "language": "python",
      "score": 55.01,
      "next": "get_symbol"
    },
    {
      "title": "Symbol: worker.workflows.IssueAnalysis",
      "page_type": "symbol_spotlight",
      "snippet": "# worker.workflows.IssueAnalysis\n\n**Kind:** class | **Defined in:** `worker/workflows.py` | **Estimated complexity:** 1\n\n```\nclass IssueAnalysis\n```\n\n## Overview\n\nАналитика по запросу (Слой C) — воркф",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "worker/workflows.py::IssueAnalysis",
      "file": "worker/workflows.py",
      "type": "page"
    },
    {
      "title": "File: shared/agent_launcher.py",
      "page_type": "file_page",
      "snippet": "нты существуют **и по отдельности, и в рамках Issue**.\nДо этого возможен был только первый режим — `IssueAnalysis` и `IssueEstimation`\nстартовали из вебхука как самостоятельные воркфлоу, а `IssueLifec",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "shared/agent_launcher.py",
      "type": "page"
    }
  ],
  "mode": "hybrid",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "8ee2a0cd85f8",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "candidates": [
    {
      "path": "worker/workflows.py"
    },
    {
      "path": "shared/repowise.py"
    },
    {
      "path": "shared/agent_launcher.py"
    }
  ],
  "exact_match": true
}

## Ход 13 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/workflows.py::IssueAnalysis"
}
```

**Ответ:**

{
  "symbol_id": "worker/workflows.py::IssueAnalysis",
  "file": "worker/workflows.py",
  "name": "IssueAnalysis",
  "kind": "class",
  "qualified_name": "worker.workflows.IssueAnalysis",
  "signature": "class IssueAnalysis",
  "language": "python",
  "start_line": 2393,
  "end_line": 2421,
  "symbol_start_line": 2393,
  "symbol_end_line": 2421,
  "source": "  2393\tclass IssueAnalysis:\n  2394\t    \"\"\"Аналитика по запросу (Слой C) — воркфлоу цепочки FNR.\n  2395\t\n  2396\t    Работает в двух режимах (#37): дочерним прогоном `IssueLifecycle`, когда\n  2397\t    цикл жив, и самостоятельным — при автономном запуске (скрипт, прогон\n  2398\t    прежнего поколения). Код один и тот же; отличается только родитель.\n  2399\t\n  2400\t    Фиксированный id `analysis-<repo>-<n>` даёт идемпотентность в обоих\n  2401\t    режимах: повторный `/analyze` упрётся в WorkflowAlreadyStarted, а не\n  2402\t    запустит второй дорогой прогон.\n  2403\t    \"\"\"\n  2404\t\n  2405\t    @workflow.run\n  2406\t    async def run(self, analyze: AnalyzeInput) -> bool:\n  2407\t        \"\"\"Возвращает, опубликованы ли артефакты.\n  2408\t\n  2409\t        Родителю этот ответ нужен, чтобы решить, можно ли передавать задачу\n  2410\t        разработчику: без аналитики передавать нечего. Автономный запуск\n  2411\t        результат просто игнорирует.\n  2412\t        \"\"\"\n  2413\t        if await _agents_off(analyze.repo, analyze.issue_number, \"/analyze\"):\n  2414\t            return False\n  2415\t        await workflow.execute_activity(\n  2416\t            activities.ack_command,\n  2417\t            analyze,\n  2418\t            start_to_close_timeout=timedelta(seconds=60),\n  2419\t            retry_policy=RetryPolicy(maximum_attempts=3),\n  2420\t        )\n  2421\t        return await _run_staged_analysis(analyze)",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 10.39,
    "index_age_days": 0,
    "indexed_commit": "8ee2a0cd85f8",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 32935
  }
}

## Ход 14 · `get_symbol` · contour

**Запрос:**

```json
{
  "symbol_id": "worker/activities.py::ClassificationExtraction"
}
```

**Ответ:**

{
  "symbol_id": "worker/activities.py::ClassificationExtraction",
  "file": "worker/activities.py",
  "name": "ClassificationExtraction",
  "kind": "class",
  "qualified_name": "worker.activities.ClassificationExtraction",
  "signature": "class ClassificationExtraction",
  "language": "python",
  "start_line": 86,
  "end_line": 88,
  "symbol_start_line": 86,
  "symbol_end_line": 88,
  "source": "    86\tclass ClassificationExtraction(BaseModel):\n    87\t    category: str = Field(description=\"EXISTING | CONSULTATION | BUG | FEATURE\")\n    88\t    answer: str",
  "truncated": false,
  "verified": true,
  "_meta": {
    "timing_ms": 12.39,
    "index_age_days": 0,
    "indexed_commit": "8ee2a0cd85f8",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false,
    "replaced_tokens": 38622
  }
}

## Ход 15 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "ADVISOR_EXISTING ADVISOR_FEATURE labels module",
  "mode": "hybrid"
}
```

**Ответ:**

{
  "results": [
    {
      "type": "symbol",
      "symbol_id": "worker/activities.py::_existing_branch",
      "name": "_existing_branch",
      "kind": "function",
      "file": "worker/activities.py",
      "start_line": 898,
      "end_line": 909,
      "signature": "def _existing_branch(repo: str, branch: str) -> str | None",
      "qualified_name": "worker.activities._existing_branch",
      "language": "python",
      "score": 10.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/label_catalog.py::ADVISOR_COLOR",
      "name": "ADVISOR_COLOR",
      "kind": "constant",
      "file": "shared/label_catalog.py",
      "start_line": 17,
      "end_line": 17,
      "signature": "ADVISOR_COLOR = \"#6E49CB\"",
      "qualified_name": "shared.label_catalog.ADVISOR_COLOR",
      "language": "python",
      "score": 10.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/label_catalog.py::ADVISOR_KINDS",
      "name": "ADVISOR_KINDS",
      "kind": "constant",
      "file": "shared/label_catalog.py",
      "start_line": 26,
      "end_line": 27,
      "signature": "ADVISOR_KINDS = (\"answered\", \"bug\", \"consultation\", \"error\",",
      "qualified_name": "shared.label_catalog.ADVISOR_KINDS",
      "language": "python",
      "score": 10.01,
      "next": "get_symbol"
    },
    {
      "title": "Symbol: shared.workflow_types.ClassificationResult",
      "page_type": "symbol_spotlight",
      "snippet": "docstring.\n\n## Decorators\n\n- `@dataclass`\n- `@dataclass`\n\n## Where it is used\n\n71 files import the module that defines it. These are import-level references, not confirmed call sites.\n\n- `scripts/bac",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "shared/workflow_types.py::ClassificationResult",
      "file": "shared/workflow_types.py",
      "type": "page"
    },
    {
      "title": "Symbol: worker.activities.classify_issue",
      "page_type": "symbol_spotlight",
      "snippet": "ие.\n\n## Decorators\n\n- `@activity.defn`\n- `@activity.defn`\n\n## Where it is used\n\n37 files import the module that defines it. These are import-level references, not confirmed call sites.\n\n- `tests/test_",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::classify_issue",
      "file": "worker/activities.py",
      "type": "page"
    }
  ],
  "mode": "hybrid",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "8ee2a0cd85f8",
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
      "path": "shared/label_catalog.py"
    },
    {
      "path": "shared/workflow_types.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches 'ADVISOR_EXISTING', 'ADVISOR_FEATURE'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}

## Ход 16 · `search_codebase` · contour

**Запрос:**

```json
{
  "query": "ADVISOR_FEATURE ADVISOR_BUG advisor:feature-request advisor:bug labels",
  "mode": "hybrid"
}
```

**Ответ:**

{
  "results": [
    {
      "title": "Symbol: shared.workflow_types.ClassificationResult",
      "page_type": "symbol_spotlight",
      "snippet": "on_synth.py`\n\n_and 46 more._\n\n## Implementation\n\n```\nclass ClassificationResult:\n    label: str  # \"advisor:existing-functionality\" | \"advisor:consultation\" | \"advisor:bug\" | \"advisor:feature-request\"",
      "relevance_score": 3.0,
      "sources": [
        "fts"
      ],
      "target_path": "shared/workflow_types.py::ClassificationResult",
      "file": "shared/workflow_types.py",
      "type": "page"
    },
    {
      "title": "Symbol: worker.activities.classify_issue",
      "page_type": "symbol_spotlight",
      "snippet": "nput, bft_on_triage: bool = False) -> ClassificationResult\n```\n\n## Overview\n\nТип запроса плюс ответ advisor комментарием.\n\n`bft_on_triage=True` глушит публикацию ответа РОВНО для запроса функционала:",
      "relevance_score": 2.951,
      "sources": [
        "fts"
      ],
      "target_path": "worker/activities.py::classify_issue",
      "file": "worker/activities.py",
      "type": "page"
    },
    {
      "title": "Symbol: tests.test_estimate_report.context",
      "page_type": "symbol_spotlight",
      "snippet": "-> EstimationContext:\n    base = dict(\n        title=\"Заголовок\",\n        body=\"Описание\",\n        labels=[\"advisor:feature-request\"],\n        thread=[],\n        branch=None,\n        artifacts={},",
      "relevance_score": 2.903,
      "sources": [
        "fts"
      ],
      "target_path": "tests/test_estimate_report.py::context",
      "file": "tests/test_estimate_report.py",
      "type": "page"
    },
    {
      "type": "symbol",
      "symbol_id": "tests/test_bft_activities.py::test_a_bug_still_gets_its_advisor_answer",
      "name": "test_a_bug_still_gets_its_advisor_answer",
      "kind": "function",
      "file": "tests/test_bft_activities.py",
      "start_line": 458,
      "end_line": 464,
      "signature": "def test_a_bug_still_gets_its_advisor_answer(monkeypatch, gh)",
      "qualified_name": "tests.test_bft_activities.test_a_bug_still_gets_its_advisor_answer",
      "language": "python",
      "score": 15.01,
      "next": "get_symbol"
    },
    {
      "type": "symbol",
      "symbol_id": "shared/label_catalog.py::ADVISOR_COLOR",
      "name": "ADVISOR_COLOR",
      "kind": "constant",
      "file": "shared/label_catalog.py",
      "start_line": 17,
      "end_line": 17,
      "signature": "ADVISOR_COLOR = \"#6E49CB\"",
      "qualified_name": "shared.label_catalog.ADVISOR_COLOR",
      "language": "python",
      "score": 10.01,
      "next": "get_symbol"
    }
  ],
  "mode": "hybrid",
  "_meta": {
    "index_age_days": 0,
    "indexed_commit": "8ee2a0cd85f8",
    "index_behind": false,
    "embedder": "mock",
    "embedder_degraded": false,
    "semantic_search": false
  },
  "candidates": [
    {
      "path": "shared/workflow_types.py"
    },
    {
      "path": "worker/activities.py"
    },
    {
      "path": "tests/test_estimate_report.py"
    },
    {
      "path": "tests/test_bft_activities.py"
    },
    {
      "path": "shared/label_catalog.py"
    }
  ],
  "exact_match": false,
  "note": "No indexed symbol exactly matches 'ADVISOR_FEATURE', 'ADVISOR_BUG'. The results are fuzzy neighbours ranked by token overlap — confirm a hit names what you meant before relying on it. If you expected an exact symbol, recheck spelling/casing, or Grep the literal name for an exhaustive usage sweep."
}
