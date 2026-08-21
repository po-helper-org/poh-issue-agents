import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# worker/ holds workflows.py, activities.py, github_client.py, llm.py
sys.path.insert(0, str(ROOT / "worker"))
# repo root holds shared/
sys.path.insert(0, str(ROOT))

import pytest

RULES_PATH = ROOT / "config" / "estimation-rules.toml"


@pytest.fixture
def rules():
    """Правила расчёта из репозитория. В контейнере тот же файл лежит по
    /app/config — тесты берут его из исходников."""
    import estimation

    return estimation.load_rules(RULES_PATH)


_FORGE_ENV = (
    "GH_TOKEN", "GITHUB_TOKEN", "GITHUB_APP_ID", "GITHUB_PRIVATE_KEY_B64",
    "GITHUB_PRIVATE_KEY_PATH", "GITHUB_INSTALLATION_ID", "GITHUB_REPOSITORY",
    "GITHUB_WEBHOOK_SECRET", "GH_PUSH_TOKEN", "GH_CLONE_TOKEN",
    "ISSUE_AGENT_REPOS", "DRY_RUN",
)


@pytest.fixture(autouse=True)
def forge_env(monkeypatch):
    """Переменные трекера не протекают между тестами.

    Раньше их ставили по месту в 17 файлах и почти нигде не убирали: тест,
    прошедший в одиночку, мог упасть в общем прогоне из-за порядка запуска.
    Фикстура снимает весь набор до теста; тест ставит только то, что ему нужно.
    """
    for name in _FORGE_ENV:
        monkeypatch.delenv(name, raising=False)


def make_fake_set_labels(add_label, remove_label):
    """Двойник `github_client.set_labels`, общий для тестов, что мокают
    `add_label`/`remove_label` по отдельности (а не транспорт целиком) и
    поэтому не могут звать настоящий `set_labels`.

    Воспроизводит её контракт: фильтр «remove минус add» (иначе новая метка
    была бы видна и в постановке, и в снятии), порядок «постановка раньше
    снятия», и раздельную строгость — снятие best-effort по каждой метке,
    сбой постановки не мешает снятию, но поднимает исключение уже после него.

    `add_label`/`remove_label` — callables с сигнатурой
    `(repo, issue_number, label)`; обычно это те же функции, что тест уже
    подменил в `github_client`, так что вызовы через `set_labels` попадают в
    те же шпионы, что и прямые вызовы add_label/remove_label.

    Это копия фильтра и строгости продукта для тестов, что не могут дойти до
    настоящего транспорта, — не сам продукт. Единственный тест, что проверяет
    реальный `github_client.set_labels` (и поймает дрейф этой копии от
    оригинала), — tests/test_set_labels.py.
    """
    def set_labels(repo, issue_number, *, add=(), remove=()):
        add = [label for label in add if label]
        keep = set(add)
        remove = [label for label in remove if label and label not in keep]
        add_error = None
        if add:
            try:
                for label in add:
                    add_label(repo, issue_number, label)
            except Exception as exc:
                add_error = exc
        for label in remove:
            try:
                remove_label(repo, issue_number, label)
            except Exception:
                pass
        if add_error is not None:
            raise add_error
    return set_labels
