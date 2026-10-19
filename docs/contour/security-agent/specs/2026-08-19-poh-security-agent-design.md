# poh-security-agent — design

Date: 2026-08-19

## Purpose

Автономный набор скиллов и наработок для security-аудита, встраиваемый в harness AI-агента (Claude Code и harness-agnostic). Ядро — Semgrep: pre-commit локальный аудит, PR-diff scan, полный scan по расписанию/push через GitHub Actions.

Ключевое требование: поставляемый набор кастомных правил — demo/шаблон (написан под конкретный Temporal/Pydantic AI B2B Sales Platform проект). Репозиторий должен быть универсальным — персонализируемым под любой целевой проект при установке. README обязан явно и заметно требовать персонализации конфига перед стартом работ.

## Non-goals

- Не заменяет Semgrep Pro / AppSec-агента (упоминается в README как опция при наличии бюджета)
- Не пытается понять бизнес-логику целевого проекта — только техстек (язык/фреймворк) для выбора наборов правил
- Первая версия не включает SCA (dependency audit) и отдельный secrets-scanner — только Semgrep-контур

## Repository structure

```
poh-security-agent/
├── README.md
├── AGENTS.md                    # harness-agnostic входная точка, дублирует суть skills/*/SKILL.md
├── LICENSE                      # MIT
├── skills/
│   ├── security-audit/SKILL.md  # /security-audit
│   └── security-setup/SKILL.md  # /security-setup
├── workflows/
│   ├── semgrep-full.yml         # копируется в .github/workflows/ целевого репо
│   └── semgrep-pr.yml
├── config/semgrep/               # demo-набор (источник: semgrep.zip), стартовый шаблон
│   ├── base/temporal-determinism.yaml
│   ├── python/{pydantic-io,async-patterns}.yaml
│   ├── typescript/react-patterns.yaml
│   ├── python-security.yaml
│   ├── python-best-practices.yaml
│   ├── typescript-security.yaml
│   ├── ai-hygiene.yaml
│   └── tests/                   # run_tests.sh + фикстуры, перенесены как есть
└── examples/
    └── personalized-config-example.md  # пример адаптации под другой стек
```

## Components

### `skills/security-audit/SKILL.md`

Триггер: `/security-audit`, "проверь код на уязвимости перед коммитом", "security scan".

Логика:
1. Ищет `config/semgrep/` в целевом (текущем) репозитории; если отсутствует — сообщает, что `/security-setup` не был запущен, использует `config/semgrep/` из самого poh-security-agent как fallback demo-набор с явным предупреждением.
2. Запускает `semgrep scan --config <path> --severity ERROR --severity WARNING --json`.
3. Если `SEMGREP_APP_TOKEN` не задан — реестровые наборы (`p/*`) всё равно доступны (community rules без auth), но Pro-фичи (AppSec агент, полный review) недоступны — это фиксируется в выводе.
4. Парсит JSON, печатает находки `file:line — message`, группирует по severity.
5. Предлагает пользователю/агенту список находок для авто-фикса; сам не правит код без явного запроса.
6. При ошибке (битый YAML, semgrep не установлен) — печатает точную причину и команду для диагностики (`semgrep --validate --config <path>`), не проглатывает молча.

### `skills/security-setup/SKILL.md`

Триггер: `/security-setup`, вызывается один раз при установке в целевой репозиторий.

Логика:
1. Определяет стек: ищет `package.json`, `pyproject.toml`/`requirements.txt`, расширения файлов (`.py`, `.ts/.tsx`, `.js/.jsx`).
2. Копирует `workflows/semgrep-full.yml` и `workflows/semgrep-pr.yml` в `.github/workflows/` целевого репо.
3. Копирует `config/semgrep/base/` всегда (общие правила).
4. Из `config/semgrep/python/`, `config/semgrep/typescript/` подключает только папки, релевантные обнаруженному стеку; остальные не копирует.
5. Правит `SEMGREP_RULES` в скопированных workflow-файлах: оставляет только пакеты `p/*`, релевантные стеку (например, убирает `p/flask`/`p/fastapi` если Python-фреймворк не обнаружен, убирает `p/react`/`p/nextjs` если нет TS/JS).
6. Печатает чек-лист пользователю: "Правила скопированы как ШАБЛОН. Проверь и удали `temporal-determinism.yaml`, если не используешь Temporal. Добавь правила под свои инварианты. Запусти `config/semgrep/tests/run_tests.sh`. Закоммить."
7. Не подключается к GitHub Secrets и не создаёт `SEMGREP_APP_TOKEN` сам — только инструктирует, где его добавить (Settings → Secrets → Actions), т.к. это токен и требует ручного действия пользователя.

### `workflows/semgrep-full.yml`, `workflows/semgrep-pr.yml`

Переносятся из предоставленных `semgrep.yml`/`semgrep-pr.yml` почти без изменений:
- `semgrep-full.yml`: push/PR/schedule(weekly)/workflow_dispatch, SARIF → GitHub Security tab, artifact upload, PR-комментарий с summary.
- `semgrep-pr.yml`: PR diff-scan (только изменённые `.py/.ts/.tsx/.js/.jsx`), быстрый фидбек, PR-комментарий, fail on ERROR findings.

Единственное изменение: `SEMGREP_RULES` из захардкоженного списка (`p/flask`, `p/fastapi`, ...) становится плейсхолдером, который `/security-setup` переписывает под стек — до персонализации остаётся demo-набор с явным комментарием в YAML `# TODO: persionalize via /security-setup or manually — see README`.

### README.md

Первый блок после заголовка — предупреждение:

> ⚠️ **Перед стартом работ — персонализируйте свой конфиг semgrep под потребности и правила вашего репозитория.**
> Поставляемый набор правил (`config/semgrep/`) — demo-конфигурация, написанная для конкретного Temporal/Pydantic проекта. Используйте `/security-setup` или сделайте это вручную перед тем как полагаться на находки скана.

Далее: Quick Start (2 шага — скопировать workflow в Actions, распаковать/подключить config), как получить Semgrep токен, что даёт Pro-версия (AppSec агент, review из коробки), структура репо, как писать свои правила (ссылка на `config/semgrep/tests/run_tests.sh`).

## Testing

- `config/semgrep/tests/run_tests.sh` переносится как есть, прогоняется в CI самого poh-security-agent (`.github/workflows/test-rules.yml`) на каждый push, чтобы демо-правила не деградировали.
- Ручная проверка: установка в тестовый target-репозиторий (пустой Python+TS проект) через `/security-setup`, проверка что copied workflow валиден (`actionlint` или `yamllint` при наличии), что `semgrep --validate` проходит.

## Out of scope for v1 (noted, not built)

- SCA / dependency audit skill
- Отдельный secrets-scanner skill (gitleaks/trufflehog) — semgrep `p/secrets` покрывает базово
- Авто-фикс находок без подтверждения пользователя
