"""Модели: одно значение на переменную, и путь `claude -p` не выбирает сам.

Класс отказа, который здесь сторожится, не ловится ни ревью, ни прогоном: обе
стороны выглядят настроенными, а работают на разных моделях. Так расходились
`MODEL_CLASSIFY` (`glm-5.2` в коде, `glm-4.6` в `.env.example`) — на стенде
побеждал compose, а всякий прогон мимо него молча уходил на модель дороже и
жёстче по лимитам.
"""

import ast
import inspect
import pathlib
import re

import pytest

import activities
import llm

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV_EXAMPLE = (ROOT / ".env.example").read_text(encoding="utf-8")


def _declared(name: str) -> str:
    """Значение переменной в `.env.example` — то, что человек скопирует в `.env`."""
    found = re.findall(rf"^{name}=(.*)$", ENV_EXAMPLE, re.M)
    assert found, f"{name} не объявлена в .env.example"
    return found[-1].strip()


@pytest.mark.parametrize("name, default", [
    ("MODEL_GATE", llm.MODEL_GATE),
    ("MODEL_CLASSIFY", llm.MODEL_CLASSIFY),
])
def test_the_code_default_matches_the_env_example(name, default):
    """Умолчание в коде и значение в `.env.example` — одно и то же.

    Разойдясь, они дают ровно ту тихую подмену модели, ради которой этот файл
    и написан: контейнер идёт по одной модели, скрипт рядом — по другой.
    """
    assert default == _declared(name)


def test_the_bft_direct_model_matches_too():
    """`BFT_DIRECT_MODEL` живёт умолчанием прямо в activities, а не в llm.py."""
    src = inspect.getsource(activities)
    found = re.findall(r'BFT_DIRECT_MODEL"\s*,\s*"([^"]+)"', src)

    assert found, "умолчание BFT_DIRECT_MODEL не найдено в activities.py"
    assert set(found) == {_declared("BFT_DIRECT_MODEL")}


def test_the_claude_path_names_its_model():
    """`claude -p` вызывается БЕЗ `--model`, поэтому модель обязана приехать
    переменной окружения. Пустая означает не «умолчание контура», а «решает
    провайдер» — и решает он в пользу самой свежей и дорогой.

    Это самый долгий путь контура (стадии FNR и БФТ идут до 900 с), и он
    единственный, где модель не названа в коде ни разу.
    """
    assert _declared("ANTHROPIC_MODEL"), "ANTHROPIC_MODEL пуста — модель выберет провайдер"


def test_the_claude_call_passes_the_environment_through():
    """Переменная доезжает до субпроцесса: `_run_claude` собирает env поверх
    `os.environ`, а не с нуля. Собирал бы с нуля — `ANTHROPIC_MODEL` не дошла
    бы, и пин в `.env` был бы декорацией."""
    tree = ast.parse(inspect.getsource(activities._run_claude))
    envs = [ast.unparse(kw.value) for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            for kw in node.keywords if kw.arg == "env"]

    assert envs, "у вызова claude нет env"
    assert any("os.environ" in e for e in envs), envs
