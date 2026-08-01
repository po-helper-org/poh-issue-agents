# Спайк: tool-calling `claude -p` через Anthropic-эндпоинт z.ai

> **Дата:** 2026-07-22
> **Задача:** Task 1 плана `docs/superpowers/plans/2026-07-22-analyze-command-layer-c.md`
> **Риск:** R-01 (высокий) из `sa_documentation/FNR/FNR_2/system_requirements.md`
> **Вердикт: 🟢 GO**

## Зачем

Вся фича `/analyze` строится на том, что `claude -p` в контейнере воркера умеет
вызывать инструменты (`Read`/`Write`/`Bash`) через Anthropic-совместимый эндпоинт
z.ai. Для GLM уже была зафиксирована несовместимость OpenAI tool-calling
(`worker/llm.py:28-30`), Anthropic-путь не проверялся. Без подтверждения весь
пайплайн FNR (5 стадий, каждая пишет файлы) нереализуем, и спека предусматривает
пивот на концепт D.

## Окружение

| Параметр | Значение |
|---|---|
| Образ | `worker` (`worker/Dockerfile`, до изменений Task 2) |
| `claude --version` | `2.1.197 (Claude Code)` |
| `ANTHROPIC_BASE_URL` | `https://api.z.ai/api/anthropic` |
| `ANTHROPIC_AUTH_TOKEN` | задан (49 символов) |
| Пользователь в контейнере | root |

## Проба 1 — `Write`

```sh
docker compose run --rm --no-deps --entrypoint sh worker -c '
  cd /tmp
  claude -p "Create a file named spike.txt containing exactly the text OK. Use the Write tool." \
    --permission-mode acceptEdits > /tmp/out.log 2>&1
  echo "claude_exit=$?"; tail -25 /tmp/out.log
  cat /tmp/spike.txt
'
```

```
claude_exit=0
Done! Created `/tmp/spike.txt` with the content `OK`.
FILE EXISTS, contents:
OK
```

## Проба 2 — `Read` + `Bash` + `Write` в одной цепочке

Промпт: прочитать `source.txt` (содержит `MAGIC_TOKEN_7431`), выполнить через Bash
`wc -l source.txt`, записать `report.txt` с токеном и числом строк.

```
claude_exit=0
Done. I read `source.txt` which contained the token `MAGIC_TOKEN_7431`, ran `wc -l`
which reported 1 line, and created `report.txt` with the content `MAGIC_TOKEN_7431 1`.
--- report.txt ---
MAGIC_TOKEN_7431 1
```

Токен и счётчик строк в артефакте доказывают, что инструменты реально исполнялись,
а не были выдуманы моделью в тексте ответа.

## Ключевая находка: флаг разрешений

Первая попытка использовала `--dangerously-skip-permissions` (как было написано в
плане и в NFR 4.3.2.4 спеки) и упала:

```
--dangerously-skip-permissions cannot be used with root/sudo privileges for security reasons
```

Контейнер воркера работает от root, поэтому этот флаг там неприменим в принципе.
Рабочий вариант — **`--permission-mode acceptEdits`**: даёт неинтерактивную запись
файлов без root-ограничения.

Следствия, внесённые в документы:

- `docs/superpowers/plans/2026-07-22-analyze-command-layer-c.md` — Task 1 Step 3 и
  реализация `_run_claude` в Task 6 переведены на `--permission-mode acceptEdits`;
  запись в Self-Review о «`--dangerously-skip-permissions` перекрывает acceptEdits»
  была неверной и исправлена.
- `sa_documentation/FNR/FNR_2/system_requirements.md` — NFR 4.3.2.4 п.5.

Побочно: в первом прогоне `echo "exit=$?"` стоял после конвейера `| tail`, поэтому
печатал код `tail`, а не `claude` — замер был недостоверным. Исправлено: код возврата
снимается до перенаправления вывода.

## Вывод

Риск R-01 снят. Концепт B реализуем, пивот на концепт D не требуется.
Единственная корректировка — флаг разрешений.
