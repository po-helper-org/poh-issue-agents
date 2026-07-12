# Установленные навыки (skills) и команды

В `.claude/skills/` и `.claude/commands/` установлены два фреймворка навыков —
их используют тяжёлые стадии обработки Issue (`run_research_pipeline` /
`run_bug_pipeline` в `worker/activities.py`, вызывающие `claude -p`).

## Superpowers — obra/superpowers

- Источник: https://github.com/obra/superpowers (MIT, © 2025 Jesse Vincent)
- Ядро инженерных навыков Claude Code: TDD, систематический дебаг, планы,
  code review, субагенты, worktrees и др.
- Навыки: `brainstorming`, `dispatching-parallel-agents`, `executing-plans`,
  `finishing-a-development-branch`, `receiving-code-review`,
  `requesting-code-review`, `subagent-driven-development`,
  `systematic-debugging`, `test-driven-development`, `using-git-worktrees`,
  `using-superpowers`, `verification-before-completion`, `writing-plans`,
  `writing-skills`.
- Примечание: как плагин Superpowers активируется SessionStart-хуком
  (`${CLAUDE_PLUGIN_ROOT}`). Здесь навыки установлены напрямую в
  `.claude/skills/` — они доступны как обычные skills. Для хук-активации
  можно дополнительно поставить его как marketplace-плагин
  (`/plugin marketplace add obra/superpowers`).

## SA-helper — System Analyst Helper

- Источник: https://gitlab.com/boboden541/sa-helper
- Фреймворк для ИИ-агентов: реверс-инжиниринг, документация, системные
  требования (BR/FR/NFR) с принципом нулевого допуска к галлюцинациям
  (Traceability до строки кода). Это тот самый SA-helper, чью техспеку
  вызывает research/bug-пайплайн этого сервиса.
- Навыки: `architectural-debate`, `architecture`, `db_archeologist`,
  `problem-analyst`, `solution-designer`, `system-analyst-sysreq`,
  `technical-documentation`.
- Команды (`.claude/commands/`): `arch-gen`, `context-gen`, `create-doc`,
  `data-trace`, `fnr-concept`, `fnr-debate`, `fnr-new-task`,
  `fnr-system-requirements`, `project-map`, `validate-doc`.
- Опционально: у SA-helper есть `indexer/` (Neo4j-граф + MCP-сервер, 13
  инструментов) — это отдельный backend, не навык; при необходимости
  подключается по инструкции из README самого SA-helper.
