---
title: Прод на внешнем Temporal ловил DNS-сбои — три именованных compose-конфига
date: 2026-07-23
kind: ops
area: deploy
prs: [14, 15]
adr: []
tags: [deploy, docker-compose, temporal]
source: retro
---

# Прод на внешнем Temporal ловил DNS-сбои — три именованных compose-конфига

## Ситуация

Переезд на централизованный Temporal: прод ловил runtime-сбои — `Connection refused`,
затем `Temporary failure in name resolution`: кластер недоступен из контейнера по DNS.

## Причина

Один базовый compose-файл с override-механикой: override не умеет удалять ключи, а прод
и дев требуют разных настроек сервисов (bind-mounts, публикация портов, сети); адрес
кластера оказался привязан к конфигурации окружения.

## Решение

Три самостоятельных именованных конфига: `docker-compose.yml` (main — приложение против
внешнего Temporal из `.env`), `docker-compose.local.yml` (local — полный стек для
офлайн-разработки), `docker-compose.full.yml` (full — self-contained прод: только `expose`,
обязательный `POSTGRES_PASSWORD`). Единая точка подключения `shared/temporal_client.py::connect_temporal()`
читает `TEMPORAL_ADDRESS`/`TEMPORAL_NAMESPACE`/`TEMPORAL_TLS` вместо четырёх инлайновых
`Client.connect` с зашитым namespace. Реальные адреса — только в `.env` развёртывания,
в репозитории плейсхолдеры. `scripts/smoke_temporal.py` — сквозная проверка очереди.

## Как проверить

`docker compose config` для каждого файла (main = 2 сервиса, local/full = 5);
`make up` / `up-local` / `up-full`.

## Уроки

Override-файлы не заменяют именованные конфигурации, когда нужны разные наборы ключей;
когда внешний сервис нестабилен из контейнера — держите self-contained вариант рядом.
