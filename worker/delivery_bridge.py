"""Точка подключения Delivery-Agent к Harness.

Delivery-Agent живёт в своём репозитории (`po-helper-org/poh-delivery-agent`) и
ставится в образ воркера пакетом. Harness не знает ни его правил, ни его
воркфлоу — он даёт ему ровно две вещи:

1. **Токен GitHub** — свой installation-токен GitHub App, через порт агента.
   Второй клиент, второе приложение и второй набор прав здесь не заводятся.
2. **Агента разработки** — активность `delivery_fix_conflicts`. Конфликт в
   ветке чинит тот же OpenHands, что пишет код по задачам; поднимать для этого
   вторую машинерию значило бы иметь два разных «агента разработки» в одном
   контуре.

Обратной зависимости нет: `poh_delivery` не импортирует ничего из Harness.
"""

import asyncio
import logging
import os
import shutil
import subprocess
from pathlib import Path

from temporalio import activity

import github_client
from shared import develop

_log = logging.getLogger(__name__)

MERGE_MESSAGE = "merge: {base} в ветку PR #{pr} (разрешение конфликтов Delivery-Agent)"


def token_provider(repo: str) -> str:
    """Токен для Delivery-Agent — тот же installation-токен GitHub App."""
    return github_client.auth_token(repo)


def install() -> None:
    """Сконфигурировать порты агента. Зовётся один раз на старте воркера."""
    from poh_delivery import integration

    integration.install(token_provider,
                        dry_run=os.environ.get("DRY_RUN", "").strip() not in ("", "0"))


# --- разрешение конфликтов ---

def _slug(repo: str, pr_number: int) -> str:
    return f"delivery-{repo.replace('/', '__')}-{pr_number}"


def _paths(repo: str, pr_number: int) -> tuple[Path, Path]:
    root = Path(develop.workspace_mount()) / _slug(repo, pr_number)
    return root, root / "repo"


def _git(clone_dir: Path, *args: str, repo: str, check: bool = True) -> subprocess.CompletedProcess:
    """git в клоне задачи. Токен идёт credential-helper'ом, не в argv.

    Тот же приём, что в `activities._clone_repo`: argv целиком попадает в текст
    исключения, а оттуда — в историю Temporal и логи; живой токен там жить не
    должен.
    """
    env = {
        **os.environ,
        "GIT_CONFIG_COUNT": "5",
        "GIT_CONFIG_KEY_0": "credential.helper",
        "GIT_CONFIG_VALUE_0": "!f() { echo username=x-access-token; echo password=$GH_DELIVERY_TOKEN; }; f",
        "GIT_CONFIG_KEY_1": "user.name",
        "GIT_CONFIG_VALUE_1": "poh-delivery-agent",
        "GIT_CONFIG_KEY_2": "user.email",
        "GIT_CONFIG_VALUE_2": "delivery-agent@users.noreply.github.com",
        "GIT_CONFIG_KEY_3": "safe.directory",
        "GIT_CONFIG_VALUE_3": str(clone_dir),
        # Каталог принадлежит раннеру (uid 10001) после handover — второй
        # safe.directory нужен для родителя, иначе git отказывается работать
        # в чужом каталоге уже после круга правок.
        "GIT_CONFIG_KEY_4": "safe.directory",
        "GIT_CONFIG_VALUE_4": "*",
        "GH_DELIVERY_TOKEN": github_client.auth_token(repo),
    }
    result = subprocess.run(["git", "-C", str(clone_dir), *args], env=env,
                            capture_output=True, text=True, timeout=600)
    if check and result.returncode != 0:
        raise RuntimeError(f"git {args[0]} → {result.returncode}: "
                           f"{(result.stdout + result.stderr)[-500:]}")
    return result


def _prepare_clone(repo: str, pr_number: int, branch: str, base: str) -> Path:
    """Клон ветки PR с историей базы — на нём и делается мерж.

    Клон полный, без `--depth`: shallow-клон не умеет мержить ветку, которой у
    него нет, а именно это здесь и требуется.
    """
    root, clone_dir = _paths(repo, pr_number)
    shutil.rmtree(root, ignore_errors=True)
    clone_dir.mkdir(parents=True, exist_ok=True)
    _git(clone_dir, "init", "--quiet", repo=repo)
    _git(clone_dir, "remote", "add", "origin", f"https://github.com/{repo}.git", repo=repo)
    _git(clone_dir, "fetch", "--quiet", "origin", branch, base, repo=repo)
    _git(clone_dir, "checkout", "--quiet", "-B", branch, f"origin/{branch}", repo=repo)
    return clone_dir


def _conflicted_files(clone_dir: Path, repo: str) -> list[str]:
    result = _git(clone_dir, "diff", "--name-only", "--diff-filter=U", repo=repo, check=False)
    return [line for line in (result.stdout or "").splitlines() if line.strip()]


def _conflict_task(repo: str, pr_number: int, base: str, files: list[str]) -> str:
    listing = "\n".join(f"- `{name}`" for name in files)
    return f"""# Разрешить конфликт слияния

Ветка этого PR (#{pr_number} в `{repo}`) разошлась с `{base}`. Мерж
`origin/{base}` уже запущен и остановлен на конфликте.

## Файлы с конфликтом

{listing}

## Что сделать

1. Разреши конфликты в перечисленных файлах: в рабочем каталоге лежат маркеры
   `<<<<<<<`, `=======`, `>>>>>>>`.
2. **Сохрани обе функциональности** — и то, что пришло из `{base}`, и то, что
   делает этот PR. Выбор «оставить свою версию целиком» почти всегда неверен:
   он молча выкидывает чужую влитую работу.
3. Ничего, кроме разрешения конфликта, не меняй: рефакторинг, переименования и
   правки соседнего кода в этот круг не входят.
4. Прогони тесты проекта и убедись, что они зелёные.
5. Коммит и пуш НЕ делай — это сделает контур после проверки.

Признак успеха: маркеров конфликта в файлах не осталось, тесты зелёные.
"""


@activity.defn(name="delivery_fix_conflicts")
async def fix_conflicts(repo: str, pr_number: int) -> str:
    """Развести конфликт ветки PR с базой. Возврат — что именно произошло.

    Сначала пробуется обычный `git merge`: изрядная часть «конфликтов» на самом
    деле расхождение, которое git сводит сам, и звать ради этого платного агента
    незачем. Агент включается только там, где git остановился.
    """
    import activities  # локальный импорт: модуль тянет весь мир воркера

    pull = await asyncio.to_thread(github_client.get_pull, repo, pr_number)
    branch = pull["head"]["ref"]
    base = pull["base"]["ref"]

    clone_dir = await activities._run_with_heartbeat(
        _prepare_clone, repo, pr_number, branch, base, label="conflict:clone")

    merge = _git(clone_dir, "merge", "--no-edit", f"origin/{base}", repo=repo, check=False)
    if merge.returncode == 0:
        _git(clone_dir, "push", "origin", f"HEAD:{branch}", repo=repo)
        return f"база `{base}` влита в ветку без конфликтов"

    files = _conflicted_files(clone_dir, repo)
    if not files:
        _git(clone_dir, "merge", "--abort", repo=repo, check=False)
        raise RuntimeError(f"мерж не прошёл, но конфликтных файлов нет: "
                           f"{(merge.stdout + merge.stderr)[-400:]}")

    (clone_dir / ".task.md").write_text(_conflict_task(repo, pr_number, base, files),
                                        encoding="utf-8")
    root, _ = _paths(repo, pr_number)
    activities._handover_to_runner(root)

    slug = _slug(repo, pr_number)
    await asyncio.to_thread(activities._reap_runner, slug)
    command = develop.runner_command(
        slug, image=develop.runner_image(), volume=develop.workspace_volume(),
        mount=develop.workspace_mount(), network=develop.proxy_network(),
        home=activities._runner_home(slug))
    env = {**os.environ, **develop.runner_env(
        os.environ.get("ZAI_API_KEY", ""), os.environ.get("ZAI_BASE_URL", ""),
        os.environ.get("DEVELOP_MODEL", "").strip() or "openai/glm-4.6")}

    def _run() -> None:
        result = subprocess.run(command, env=env, capture_output=True, text=True,
                                timeout=develop.run_timeout())
        if result.returncode != 0:
            tail = ((result.stdout or "") + (result.stderr or ""))[-1500:]
            raise RuntimeError(f"агент разработки сорвался (код {result.returncode}): {tail}")

    await activities._run_with_heartbeat(_run, label="conflict:agent")

    still = _conflicted_files(clone_dir, repo)
    if still:
        _git(clone_dir, "merge", "--abort", repo=repo, check=False)
        raise RuntimeError("после круга правок конфликт остался в: " + ", ".join(still))

    (clone_dir / ".task.md").unlink(missing_ok=True)
    _git(clone_dir, "add", "-A", repo=repo)
    _git(clone_dir, "commit", "--no-edit", "-m",
         MERGE_MESSAGE.format(base=base, pr=pr_number), repo=repo)
    _git(clone_dir, "push", "origin", f"HEAD:{branch}", repo=repo)
    await asyncio.to_thread(
        github_client.post_comment, repo, pr_number,
        f"**Delivery-Agent: конфликт с `{base}` разрешён.**\n\n"
        f"Файлы: {', '.join(f'`{name}`' for name in files)}. "
        f"Ветка обновлена, PR возвращается в релизную очередь после перепроверки.")
    return f"конфликт разрешён агентом разработки в {len(files)} файл(ах)"


HARNESS_ACTIVITIES = [fix_conflicts]
