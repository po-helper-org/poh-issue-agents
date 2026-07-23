# FNR-3: Кластеризация бэклога не группирует под поставку — вырождается в одиночки

> **Тип:** Архитектурное изменение (кластеризация) / доработка consolidation
> **Дата:** 2026-07-15
> **Статус:** Открыта
> **Примечание:** FNR-2 (сборка consolidation-этапа) задокументирована как
> `docs/superpowers/specs/2026-07-14-issue-consolidation-design.md` + план, без
> отдельной папки `FNR_2/`. Эта задача — следующая итерация того же этапа.

---

## 1. Постановка проблемы

Consolidation-этап должен группировать Issue бэклога так, чтобы одна техническая
итерация и релиз закрывали максимум схожих требований (кластер = единица поставки).
Фактически `cluster_profiles` кластеризует по строке `proposed_mechanism` каждого
Issue и на реальном бэклоге `po-helper-org/poh-helper` (75 open) выдаёт
**вырожденный результат — 54 кластера-одиночки** (0 групп из ≥2 связанных Issue,
кроме единичных пар). Цель — «объединить похожие в один Issue на проработку» — не
достигается.

## 2. Контекст

`cluster_profiles` — reduce-стадия пайплайна `ConsolidationWorkflow`
(profile-extract → **cluster** → synth → PR). На вход получает список
`SolutionProfile`, каждый с полем `proposed_mechanism` (строка «как Issue
предлагает решать»), извлечённым пер-Issue в `extract_solution_profile`. Кластеризация
просит LLM (glm через z.ai) сгруппировать профили; исход материализуется 1:1 в
`Cluster`.

Проявляется на любом прогоне с бэклогом >~10 разнородных Issue. Подтверждено
дважды: single-shot reduce (первая версия) и map-reduce по батчам (текущая) — оба
дали ~54 одиночки. Полный разбор — `docs/consolidation-clustering-study.md`.

## 3. Текущее поведение (As-Is)

`cluster_profiles` строит листинг из `proposed_mechanism`/`target`/`domain` и
передаёт его в один (или, при батчах, несколько) LLM-вызов на извлечение
`ClusterExtraction`. Модель, получив ~57 уникальных строк механизма, возвращает
почти по одному кластеру на Issue.

**Цепочка событий (от симптома к корню):**

| Шаг | Компонент | Что происходит | Доказательство |
|-----|-----------|---------------|----------------|
| 1 | `extract_solution_profile` | Извлекает `proposed_mechanism` пер-Issue — формулировка уникальна почти у каждого («jira-indexator», «jira-sync gantt», «mass JIRA ops») | `worker/consolidation_activities.py:26-38` |
| 2 | `_cluster_call` | Кормит модели листинг механизмов, просит `ClusterExtraction` | `worker/consolidation_activities.py:80-87` |
| 3 | `cluster_profiles` | Материализует ровно то, что вернула модель, 1:1 в `Cluster` (никакой доменной коррекции) | `worker/consolidation_activities.py:123-145` |
| 4 | `system_cluster.md` | Просит группировать по «общему mechanism» — а механизмы уже гранулярны | `prompts/system_cluster.md` |
| 5 | Результат прогона | 75 open → 54 кластера, распределение `{1: 54}` (все одиночки) | `docs/consolidation-clustering-study.md` §1,§Приложение |

**Ключевые компоненты:**

| Компонент | Роль | Файл:строка |
|-----------|------|-------------|
| `cluster_profiles` | Reduce-стадия кластеризации | `worker/consolidation_activities.py:123` |
| `_cluster_call` | Один LLM-вызов кластеризации над листингом механизмов | `worker/consolidation_activities.py:80` |
| `_merge_local` | Merge батч-локальных кластеров (map-reduce) | `worker/consolidation_activities.py:89` |
| `proposed_mechanism` | Поле-ключ группировки (слишком гранулярное) | `shared/workflow_types.py` (`SolutionProfile`) |
| `system_cluster.md` | Промпт: «группируй по общему механизму» | `prompts/system_cluster.md` |
| `ConsolidationWorkflow.run` | Вызывает `cluster_profiles` как единый activity | `worker/consolidation_workflow.py` |

## 4. Корень проблемы

Причина не в таймаутах и не в размере батча, а в **оси группировки и постановке
задачи модели**:

1. **Неверная ось.** Кластеризация идёт по семантике строки `proposed_mechanism`,
   а не по единице поставки («что реализуется/релизится вместе»). Два JIRA-Issue с
   разными формулировками механизма поставляются одним движком, но по строке —
   «разные».
2. **Слишком гранулярный ключ.** `proposed_mechanism` извлекается пер-Issue и почти
   всегда уникален → модель видит ~57 различных механизмов → ~57 кластеров.
3. **Открытая кластеризация — слабое место LLM.** Просьба «сгруппируй N элементов»
   без заданного словаря вырождается в 1-кластер-на-элемент; map-reduce усугубляет
   (батчи разносят связанные Issue, merge их не собирает).

**Доказательство, что данные группируемы:** тот же бэклог при taxonomy-first
(вывести малый словарь зон → классифицировать) даёт 8 осмысленных зон по 6–14 Issue
(эксперимент, `docs/consolidation-clustering-study.md` §Приложение). Значит дефект —
в методе `cluster_profiles`, не в бэклоге.

## 5. Ожидаемое поведение

Кластеризация группирует Issue в **зоны поставки** так, что каждая зона —
кандидат на охват одной технической итерацией/релизом (5–15 Issue на зону на
реальном бэклоге), с возможностью нарезки крупной зоны на инкременты (MVP/MVP+1) по
зависимостям и потолку размера. Сквозные Issue — множественное членство (primary +
secondary). Инварианты сохраняются: #111 target-guard, anchors-провенанс. Конкретный
механизм (taxonomy-first: derive → assign → slice) — предмет концепта
(`/fnr-concept`); здесь фиксируется только разрыв.

## 6. Зона воздействия

**Прямое воздействие:**

| Компонент | Тип | Файл |
|-----------|-----|------|
| `cluster_profiles` / `_cluster_call` / `_merge_local` | activity + хелперы (заменяются) | `worker/consolidation_activities.py` |
| `ClusterExtraction`/`ClusterOut`/`MemberOut`/`MergeExtraction` | схемы кластеризации | `worker/consolidation_activities.py:42-71` |
| `system_cluster.md` / `system_cluster_merge.md` | промпты кластеризации | `prompts/` |
| `ConsolidationWorkflow.run` | оркестратор reduce-стадии | `worker/consolidation_workflow.py` |

**Косвенное воздействие:**

| Компонент | Зависимость | Риск |
|-----------|------------|------|
| `synthesize_unifying_issue` | Работает над `Cluster` — при переходе к зонам/инкрементам меняется вход | Сигнатура/поля могут потребовать правки (`worker/consolidation_activities.py`) |
| `write_consolidation_pr` / `_render_overview` | Рендерит `ClusterSet` | Формат overview зависит от новой модели зон |
| `SolutionProfile.proposed_mechanism` | Перестаёт быть ключом группировки | Возможно избыточно или требует более абстрактного поля (domain/capability) |
| История workflow (replay) | Зоны как ярлыки легче, чем тяжёлые объекты | Смежный выигрыш; см. FNR по replay-масштабу |

**Защищённые компоненты (не ломать):**

- `extract_solution_profile` (профили — полезны как есть) и его тесты.
- Инварианты #111 (target-divergence) и множественное членство.
- Контракт `write_consolidation_pr`: только PR, никаких мутаций Issue, DRY_RUN-guard.

## 7. Ограничения

- Кластеризация исполняется LLM (glm через z.ai) с жёстким rate-limit — число и
  размер вызовов ограничены; открытая кластеризация над всем набором ненадёжна.
- Ось поставки в идеале опирается на карту компонентов/`capabilities.md` — её
  полнота ограничена; при отсутствии зона привязывается к предполагаемой поверхности.
- «Одна итерация» имеет потолок размера — крупная зона не равна одному релизу
  (нужна нарезка), это часть ожидаемого поведения, не отдельная задача.
- Сохранить обратную совместимость по PR-контракту и не мутировать GitHub Issue.

## 8. Ссылки

| Артефакт | Путь |
|----------|------|
| Изучение практик группировки + эксперимент | `docs/consolidation-clustering-study.md` |
| Дизайн consolidation (FNR-2) | `docs/superpowers/specs/2026-07-14-issue-consolidation-design.md` |
| План реализации consolidation | `docs/superpowers/plans/2026-07-14-issue-consolidation.md` |
| Текущий код кластеризации | `worker/consolidation_activities.py:42-145` |
| Оркестратор | `worker/consolidation_workflow.py` |

---

> Задача FNR-3 описана. Следующий шаг: `/fnr-concept sa_documentation/FNR/FNR_3/task.md`
