#!/usr/bin/env bash
# Стенд харнесса БФТ на сервере (docs/BFT-HARNESS.md, #329): Gitea 28 + Temporal start-dev.
# Запускать под aleks, идемпотентно:
#   bash ~/Projects/poh-issue-agents/deploy/bft-harness/install-stand.sh
# Без Docker и Postgres: бинарники + SQLite, user-юниты с MemoryMax. Секреты — в ~/.config/bft-harness (600),
# в вывод не печатаются.
set -euo pipefail

GITEA_VER=28.1.0
TEMPORAL_VER=1.9.1
BASE="$HOME/.local/share/bft-harness"
CONF="$HOME/.config/bft-harness"
UNITS="$HOME/.config/systemd/user"
DIR="$(cd "$(dirname "$0")" && pwd)"
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
[ "$(id -un)" = aleks ] || { echo "Запускать под aleks"; exit 1; }
install -d -m 700 "$CONF"
install -d "$BASE/bin" "$BASE/gitea" "$BASE/temporal" "$UNITS"
secret() { install -m 600 /dev/null "$1"; setfacl -b "$1" 2>/dev/null || true; }
gen() { head -c 32 /dev/urandom | base64 | tr -d '/+=\n'; }

echo "== 1/5 Gitea $GITEA_VER"
if ! "$BASE/bin/gitea" --version 2>/dev/null | grep -q "$GITEA_VER"; then
  T=$(mktemp -d)
  curl -fsSL -o "$T/gitea.xz" "https://dl.gitea.com/gitea/$GITEA_VER/gitea-$GITEA_VER-linux-amd64.xz"
  curl -fsSL -o "$T/gitea.xz.sha256" "https://dl.gitea.com/gitea/$GITEA_VER/gitea-$GITEA_VER-linux-amd64.xz.sha256"
  (cd "$T" && echo "$(cut -d' ' -f1 gitea.xz.sha256)  gitea.xz" | sha256sum -c --quiet)
  xz -d "$T/gitea.xz" && install -m 755 "$T/gitea" "$BASE/bin/gitea" && rm -rf "$T"
fi
"$BASE/bin/gitea" --version | head -1

echo "== 2/5 Temporal CLI $TEMPORAL_VER"
if ! "$BASE/bin/temporal" --version 2>/dev/null | grep -q "$TEMPORAL_VER"; then
  T=$(mktemp -d)
  F="temporal_cli_${TEMPORAL_VER}_linux_amd64.tar.gz"
  curl -fsSL -o "$T/$F" "https://github.com/temporalio/cli/releases/download/v$TEMPORAL_VER/$F"
  curl -fsSL -o "$T/checksums.txt" "https://github.com/temporalio/cli/releases/download/v$TEMPORAL_VER/checksums.txt"
  (cd "$T" && grep " $F\$" checksums.txt | sha256sum -c --quiet)
  tar -xzf "$T/$F" -C "$T" temporal && install -m 755 "$T/temporal" "$BASE/bin/temporal" && rm -rf "$T"
fi
"$BASE/bin/temporal" --version | head -1

echo "== 3/5 Настройки Gitea"
INI="$BASE/gitea/app.ini"
if [ ! -s "$INI" ]; then
  secret "$INI"
  sed -e "s|@BASE@|$BASE|g" -e "s|@SECRET_KEY@|$(gen)|" -e "s|@INTERNAL_TOKEN@|$(gen)$(gen)|" \
      "$DIR/gitea-app.ini" >> "$INI"
fi

echo "== 4/5 Юниты"
for u in bft-gitea bft-temporal; do
  sed "s|@BASE@|$BASE|g" "$DIR/$u.service" > "$UNITS/$u.service"
done
systemctl --user daemon-reload
systemctl --user enable -q --now bft-gitea bft-temporal
for _ in $(seq 1 30); do curl -sf -o /dev/null http://127.0.0.1:8650/api/healthz && break; sleep 1; done
curl -sf http://127.0.0.1:8650/api/healthz >/dev/null || { journalctl --user -u bft-gitea -n 20 --no-pager; exit 1; }
for _ in $(seq 1 30); do "$BASE/bin/temporal" operator cluster health --address 127.0.0.1:7233 >/dev/null 2>&1 && break; sleep 1; done
"$BASE/bin/temporal" operator cluster health --address 127.0.0.1:7233

echo "== 5/5 Бот, организация bft, репозиторий requests"
G="$BASE/bin/gitea --config $INI --work-path $BASE/gitea"
if ! $G admin user list 2>/dev/null | awk '{print $2}' | grep -qx bft-bot; then
  $G admin user create --username bft-bot --email bft-bot@localhost --random-password --admin \
     --must-change-password=false >/dev/null
  echo "бот bft-bot создан"
fi
TOK="$CONF/gitea-token"
if [ ! -s "$TOK" ]; then
  secret "$TOK"
  $G admin user generate-access-token --username bft-bot --token-name harness --raw \
     --scopes "write:issue,write:repository,write:organization,read:user" > "$TOK"
  echo "токен бота — $TOK (600)"
fi
api() { curl -sf -H @<(printf 'Authorization: token %s' "$(cat "$TOK")") -H 'Content-Type: application/json' "$@"; }
api http://127.0.0.1:8650/api/v1/orgs/bft >/dev/null 2>&1 || \
  api -X POST -d '{"username":"bft","visibility":"private","full_name":"Харнесс БФТ"}' http://127.0.0.1:8650/api/v1/orgs >/dev/null
api http://127.0.0.1:8650/api/v1/repos/bft/requests >/dev/null 2>&1 || \
  api -X POST -d '{"name":"requests","private":true,"auto_init":true,"description":"Inbox харнесса БФТ: задача = карточка требования"}' \
      http://127.0.0.1:8650/api/v1/orgs/bft/repos >/dev/null
# Учётка приёма: от неё сервисы (бот @bft, синхронизация с Jira, перенос) заводят карточки.
# Ботом контур считает только bft-bot — карточки от bft-bot prefilter отбросил бы как «bot» (smoke T1, #3).
if ! $G admin user list 2>/dev/null | awk '{print $2}' | grep -qx bft-intake; then
  $G admin user create --username bft-intake --email bft-intake@localhost --random-password \
     --must-change-password=false >/dev/null
  echo "учётка приёма bft-intake создана"
fi
ITOK="$CONF/intake-token"
if [ ! -s "$ITOK" ]; then
  secret "$ITOK"
  $G admin user generate-access-token --username bft-intake --token-name intake --raw \
     --scopes "write:issue,read:repository" > "$ITOK"
fi
api -X PUT -d '{"permission":"write"}' http://127.0.0.1:8650/api/v1/repos/bft/requests/collaborators/bft-intake >/dev/null
api http://127.0.0.1:8650/api/v1/repos/bft/requests | python3 -c 'import json,sys; d=json.load(sys.stdin); print("репо", d["full_name"], "private" if d["private"] else "PUBLIC")'
free -m | sed -n 2p
