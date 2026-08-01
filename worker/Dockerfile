FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl git ca-certificates gnupg \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y gh \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g @anthropic-ai/claude-code repomix \
    && rm -rf /var/lib/apt/lists/*

# TODO: установка deb8flow — подставь реальный способ (pip/бинарь/build).

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
