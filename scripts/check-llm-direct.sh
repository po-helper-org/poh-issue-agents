#!/usr/bin/env bash
# check-llm-direct — прямой вызов LLM-провайдера вне профиля Hermes запрещён (ADR 0016).
#
# Каноническая версия: po-helper-org/.github → scripts/check-llm-direct.sh
# В репозиториях лежит вендор-копия; при изменении стандарта обновляется вместе
# со стандартом po-helper-org/.github/LLM-VIA-HERMES.md.
#
# Что считается нарушением:
#   1) адрес прямого вызова LLM-провайдера в коде/конфиге:
#      api.z.ai, bigmodel.cn, api.openai.com, api.anthropic.com,
#      router.requesty.ai, openrouter.ai, api.deepseek.com, api.mistral.ai,
#      api.x.ai, api.groq.com, generativelanguage.googleapis.com;
#   2) импорт SDK провайдера (openai, anthropic) вне allowlist.
#
# Исключения (осознанные, с причиной, ревьюятся в PR):
#   - файл .github/llm-direct-allow.txt: строка вида
#       path/to/file            # причина (обязательно)
#       path/to/file.py:150     # только строка 150
#       path/to/dir/            # каталог целиком
#   - inline-маркер «llm-direct: allow» в комментарии в пределах ±1 строки
#     от совпадения (на той же строке, строкой выше или ниже).
#
# Markdown (*.md) и каталог docs/ не проверяются: описания и исследования — не код.
#
# Выход: 0 — чисто, 1 — есть нарушения. Полный список — в выводе и в $GITHUB_STEP_SUMMARY.

set -uo pipefail

cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

# Собственный путь: скрипт не проверяет сам себя (в комментариях перечислены хосты)
SELF_PATH="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

ALLOW_FILE=".github/llm-direct-allow.txt"

# Хосты прямых вызовов LLM (ADR 0016: только через http://127.0.0.1:8642/p/<profile>/…)
HOST_RE='api\.z\.ai|bigmodel\.cn|api\.openai\.com|api\.anthropic\.com|router\.requesty\.ai|openrouter\.ai|api\.deepseek\.com|api\.mistral\.ai|api\.x\.ai|api\.groq\.com|generativelanguage\.googleapis\.com'

# Импорты SDK провайдеров: сам по себе SDK не запрещён, но дефолт уходит
# провайдеру напрямую — поэтому требует явного allowlist с причиной.
IMPORT_RE='^[[:space:]]*(import[[:space:]]+openai|from[[:space:]]+openai|import[[:space:]]+anthropic|from[[:space:]]+anthropic|const[[:space:]].*=.*require\(["'"'"']openai|require\(["'"'"']openai|from[[:space:]]+["'"'"']openai|const[[:space:]].*=.*require\(["'"'"']anthropic|require\(["'"'"']anthropic|from[[:space:]]+["'"'"']anthropic)'

# Не код и не наши вызовы
EXCLUDES=(--exclude-dir=.git --exclude-dir=node_modules --exclude-dir=.venv --exclude-dir=venv
          --exclude-dir=dist --exclude-dir=build --exclude-dir=.dsh-data --exclude-dir=vendor
          --exclude='*.md' --exclude='*.lock' --exclude='package-lock.json' --exclude='pnpm-lock.yaml'
          --exclude='yarn.lock' --exclude='poetry.lock' --exclude='skills-lock.json')

# --- allowlist ---------------------------------------------------------------
declare -a ALLOW_PATHS=()
if [ -f "$ALLOW_FILE" ]; then
  while IFS= read -r line; do
    entry="${line%%#*}"                      # срезать комментарий
    entry="$(printf '%s' "$entry" | sed 's/[[:space:]]*$//;s/^[[:space:]]*//')"
    [ -z "$entry" ] && continue
    case "$entry" in
      /*|*..*) echo "FATAL: подозрительная строка allowlist: $entry" >&2; exit 2 ;;
    esac
    ALLOW_PATHS+=("$entry")
  done < "$ALLOW_FILE"
fi

allowed() {  # $1 = path, $2 = line (или пусто)
  local p="$1" ln="${2:-}" e
  for e in "${ALLOW_PATHS[@]}"; do
    [ -z "$e" ] && continue
    if [ "$p" = "$e" ]; then return 0; fi                                  # файл целиком
    if [ -n "$ln" ] && [ "$p:$ln" = "$e" ]; then return 0; fi              # файл:строка
    case "$e" in */) case "$p" in "$e"*) return 0 ;; esac ;; esac          # каталог/
  done
  return 1
}

# --- скан --------------------------------------------------------------------
mapfile -t FILES < <(git ls-files 2>/dev/null | grep -vE '^(\.git/|node_modules/|\.venv/|venv/|dist/|build/|\.dsh-data/|vendor/)|\.md$|\.lock$|package-lock\.json|pnpm-lock\.yaml|yarn\.lock|poetry\.lock|skills-lock\.json' || true)

viol=0
viol_list=""
allow_hit=0

# маркер на строке разрешает её; standalone-комментарий — ещё и следующую строку
marker_allows() {  # $1=file $2=markers("n:content …") $3=line
  local m ln_content first_char
  for m in $2; do
    ln_content="${m%%:*}"
    m="${m#*:}"
    [ -z "$ln_content" ] && continue
    if [ "$ln_content" = "$3" ]; then return 0; fi                       # маркер на той же строке
    if [ "$ln_content" = "$(($3-1))" ]; then                               # standalone-комментарий выше
      first_char="$(printf '%s' "$m" | sed 's/^[[:space:]]*//' | cut -c1)"
      case "$first_char" in '#'|'/') return 0 ;; esac
    fi
  done
  return 1
}

for f in "${FILES[@]}"; do
  [ -f "$f" ] || continue
  # не проверять сам скрипт (в его комментариях перечислены хосты провайдеров)
  [ "$(cd "$(dirname "$f")" && pwd)/$(basename "$f")" = "$SELF_PATH" ] && continue
  # не проверять allowlist: причины в нём упоминают хосты провайдеров текстом
  [ "$f" = "$ALLOW_FILE" ] && continue
  # номера строк с inline-маркером (содержимое — для standalone-проверки)
  markers=$(grep -nF 'llm-direct: allow' "$f" 2>/dev/null | tr '\n' ' ')
  hits=$(grep -nE "$HOST_RE" "${EXCLUDES[@]}" "$f" 2>/dev/null)
  hits+=$'\n'"$(grep -nE "$IMPORT_RE" "$f" 2>/dev/null)"
  [ -z "$(printf '%s' "$hits" | tr -d '[:space:]')" ] && continue
  while IFS= read -r h; do
    [ -z "$h" ] && continue
    ln="${h%%:*}"
    text="${h#*:}"
    if allowed "$f" "$ln"; then allow_hit=$((allow_hit+1)); continue; fi
    if [ -n "$markers" ] && marker_allows "$f" "$markers" "$ln"; then
      allow_hit=$((allow_hit+1)); continue
    fi
    viol=$((viol+1))
    viol_list+="  $f:$ln: $(printf '%s' "$text" | sed 's/^[[:space:]]*//' | cut -c1-160)"$'\n'
  done <<EOF
$hits
EOF
done

if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  {
    echo "## llm-direct-check (ADR 0016)"
    if [ "$viol" -gt 0 ]; then
      echo "**❌ Прямые вызовы LLM вне профиля Hermes: $viol**"
      echo '```'
      printf '%s' "$viol_list"
      echo '```'
    else
      echo "**✅ Прямых вызовов LLM-провайдеров нет** (разрешено allowlist/маркерами: $allow_hit совпадений)."
    fi
  } >> "$GITHUB_STEP_SUMMARY"
fi

if [ "$viol" -gt 0 ]; then
  echo "❌ Прямые вызовы LLM вне профиля Hermes (ADR 0016): $viol"
  printf '%s' "$viol_list"
  echo
  echo "Правило: все обращения к LLM — только через профиль Hermes http://127.0.0.1:8642/p/<profile>/v1/…"
  echo "со страницей X-Hermes-Feature: <service>/<feature>. Стандарт: po-helper-org/.github LLM-VIA-HERMES.md."
  echo "Легитимное исключение — строка в .github/llm-direct-allow.txt или маркер «llm-direct: allow»"
  echo "в комментарии рядом со строкой (причина обязательна: откат, фиксстура теста, транспорт пилота)."
  exit 1
fi

echo "✅ Прямых вызовов LLM-провайдеров нет (ADR 0016); allow-исключений сработало: $allow_hit."
exit 0
