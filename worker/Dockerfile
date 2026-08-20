FROM python:3.12-slim

# Node ТОТ ЖЕ, что у раннера и у CI целевого репозитория. Воркер прогоняет
# `DEVELOP_TEST_COMMAND` — ту же строку, что гоняет CI, — и разъехавшаяся
# мажорная версия означает «проверки красные здесь и зелёные там». На живом
# прогоне это дало `Could not find 'tests/*.test.mjs'`: glob в `node --test`
# раскрывает сам Node, и только начиная с 22.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl git ca-certificates gnupg \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y gh \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g @anthropic-ai/claude-code repomix \
    && rm -rf /var/lib/apt/lists/*

# Только КЛИЕНТ Docker (`docker-ce-cli`), без демона: одноразовый контейнер
# агента разработки поднимает сам воркер через смонтированный сокет хоста.
#
# Сокет без клиента не даёт ничего, и по конфигу это незаметно: том на месте,
# образ раннера собран, `DEVELOP_MODE=local`. А `docker run` падал на
# FileNotFoundError ещё до первой строки кода агента — снаружи `phase:failed`
# на самом дорогом шаге, одинаковый и для «агент не справился», и для «агента
# не запускали вовсе».
RUN curl -fsSL https://download.docker.com/linux/debian/gpg \
        -o /usr/share/keyrings/docker.asc \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# TODO: установка deb8flow — подставь реальный способ (pip/бинарь/build).

# entire — трекер сессий агента. Ставит хуки Claude Code и складывает диалог
# стадий чекпоинтами в git-рефы, то есть в сам репозиторий задачи: ветка
# `entire/<hash>` уезжает в origin рядом с артефактами, и по id сессии прогон
# поднимается там, где оборвался. Аккаунт для этого не нужен — запись локальная.
#
# Версия зафиксирована: install.sh тянет последнюю, и молчаливое обновление
# посреди прогонов меняло бы формат чекпоинтов под ногами.
ENV ENTIRE_VERSION=0.10.2
RUN curl -fsSL https://entire.io/install.sh | bash \
    && /root/.local/bin/entire version | head -1
ENV PATH="/root/.local/bin:${PATH}"

# Скиллы и FNR-команды SA-helper кладём в ПОЛЬЗОВАТЕЛЬСКИЙ ~/.claude, а не в
# проектный .claude: `claude -p` запускается с cwd внутри КЛОНА целевого
# репозитория, у которого может быть свой .claude — проектный каталог бы его
# перекрыл. Пользовательский уровень виден из любого cwd и не конфликтует.
COPY .claude/skills /root/.claude/skills
COPY .claude/commands /root/.claude/commands

WORKDIR /app
COPY worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY worker/ .
COPY shared/ /app/shared/
# Та же диагностика доступна и из воркера: у него своё окружение (креды claude -p,
# ZAI_*), и расходиться с вебхуком оно может незаметно.
COPY scripts/ /app/scripts/

# Промпты, коэффициенты расчёта и справочник функционала запекаются в образ,
# а не приезжают монтированием. На Dokploy каталог репозитория очищается при
# автодеплое, и bind-монтирование из него оставило бы воркер без файлов —
# _load_prompt упал бы на FileNotFoundError уже на первой стадии.
# Локальный docker-compose.yml всё ещё монтирует эти каталоги поверх, так что
# правка промпта видна без пересборки образа.
COPY prompts/ /app/prompts/
COPY config/ /app/config/
COPY workspace/ /app/workspace/

ENV PYTHONPATH=/app

CMD ["python", "worker.py"]
