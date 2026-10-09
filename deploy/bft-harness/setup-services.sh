#!/usr/bin/env bash
# Webhook и worker харнесса БФТ поверх стенда (install-stand.sh). Под aleks, идемпотентно:
#   bash ~/Projects/poh-issue-agents/deploy/bft-harness/setup-services.sh
# Окружение — ~/.config/bft-harness/harness.env (600): ключ Z.AI копируется из .env Hermes, значения не печатаются.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
CONF="$HOME/.config/bft-harness"
ENVF="$CONF/harness.env"
UNITS="$HOME/.config/systemd/user"
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
[ "$(id -un)" = aleks ] || { echo "Запускать под aleks"; exit 1; }
gen() { head -c 32 /dev/urandom | base64 | tr -d '/+=\n'; }

echo "== 1/3 Окружение ($ENVF)"
SECRET_FILE="$CONF/gitea-webhook-secret"
[ -s "$SECRET_FILE" ] || { install -m 600 /dev/null "$SECRET_FILE"; setfacl -b "$SECRET_FILE" 2>/dev/null || true; gen > "$SECRET_FILE"; }
install -m 600 /dev/null "$ENVF.tmp"; setfacl -b "$ENVF.tmp" 2>/dev/null || true
{
  echo "TEMPORAL_ADDRESS=127.0.0.1:7233"
  echo "TEMPORAL_NAMESPACE=default"
  echo "ISSUE_AGENT_REPOS=bft/requests"
  echo "GITEA_REPOS=bft/*"
  echo "GITEA_URL=http://127.0.0.1:8650"
  echo "GITEA_BOT_LOGIN=bft-bot"
  echo "GITEA_TOKEN=$(cat "$CONF/gitea-token")"
  echo "GITEA_WEBHOOK_SECRET=$(cat "$SECRET_FILE")"
  # GitHub-путь вебхука в харнессе не используется, но переменная читается при доставке на /webhook
  echo "GITHUB_WEBHOOK_SECRET=$(gen)"
  echo "ZAI_BASE_URL=https://api.z.ai/api/coding/paas/v4"
  grep -m1 '^ZAI_API_KEY=' "$HOME/.hermes/.env"
  # стадии разработки, релиза и приёмки в харнессе БФТ выключены (docs/BFT-HARNESS.md, «Вне объёма»)
  echo "DEVELOP_ENABLED=0"
  echo "DEVELOP_AUTOSTART=0"
  echo "RESEARCH_AUTOSTART=0"
  echo "HOWTODEMO_AUTOSTART=0"
  echo "BFT_ON_TRIAGE=0"
} >> "$ENVF.tmp"
mv "$ENVF.tmp" "$ENVF"
grep -c '^ZAI_API_KEY=.\+' "$ENVF" >/dev/null || { echo "нет ZAI_API_KEY в ~/.hermes/.env"; exit 1; }
echo "ok: $(cut -d= -f1 "$ENVF" | tr '\n' ' ')"

echo "== 2/3 Юниты"
for u in bft-webhook bft-worker; do sed "s|@REPO@|$REPO|g" "$REPO/deploy/bft-harness/$u.service" > "$UNITS/$u.service"; done
systemctl --user daemon-reload
systemctl --user enable -q bft-webhook bft-worker
systemctl --user restart bft-webhook bft-worker
sleep 6
systemctl --user is-active bft-webhook bft-worker

echo "== 3/3 Веб-хук Gitea → 127.0.0.1:8651/gitea/webhook"
TOK="$CONF/gitea-token"; A="http://127.0.0.1:8650/api/v1/repos/bft/requests/hooks"
api() { curl -sf -H @<(printf 'Authorization: token %s' "$(cat "$TOK")") -H 'Content-Type: application/json' "$@"; }
for id in $(api "$A" | python3 -c 'import json,sys; [print(h["id"]) for h in json.load(sys.stdin)]'); do api -X DELETE "$A/$id"; done
python3 - "$SECRET_FILE" > "$CONF/.hook.json" <<'PY'
import json, sys
print(json.dumps({"type": "gitea", "active": True, "events": ["issues", "issue_comment", "issue_label"],
                  "config": {"url": "http://127.0.0.1:8651/gitea/webhook", "content_type": "json",
                             "secret": open(sys.argv[1]).read().strip()}}))
PY
api -X POST --data @"$CONF/.hook.json" "$A" >/dev/null && rm -f "$CONF/.hook.json" && echo "веб-хук заведён"
journalctl --user -u bft-worker -n 5 --no-pager -o cat
