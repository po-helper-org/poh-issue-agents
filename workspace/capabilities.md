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
