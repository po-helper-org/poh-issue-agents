# Истории прогонов для проверки детерминизма

Здесь лежат сжатые истории реальных прогонов Temporal. Тест
`tests/test_workflow_replay.py` проигрывает каждую против текущего кода
воркфлоу и падает, если код принял бы другое решение, чем записано в истории.

Это защита от класса, который стоил контуру 28 мёртвых прогонов: правка
решения воркфлоу без `workflow.patched(...)` не ломает ни один тест, но
останавливает все идущие прогоны — и снаружи они выглядят живыми.

## Как добавить историю

    ssh poh-stand "docker exec compose-connect-redundant-system-mzso3q-temporal-1 \
      temporal workflow show --address=compose-connect-redundant-system-mzso3q-temporal-1:7233 \
      -w '<workflow-id>' -o json" > /tmp/hist.json

    grep -cE "ghs_|ghp_|Bearer |PRIVATE KEY|api_key" /tmp/hist.json   # обязан быть 0

    gzip -c /tmp/hist.json > tests/replay/histories/<workflow-id с / → __>.json.gz

Имя файла — идентификатор прогона, где `/` заменён на `__`.

## Что держать здесь

Не все истории, а разнообразные: по одной на каждую форму пути (парковка,
автостарт, дочерний прогон разработки, круг правок). Дубликаты одной формы
ничего не добавляют, а вес репозитория растёт.
