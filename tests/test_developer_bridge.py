"""Мост к стадии «Разработка»: что контур ей обещает и чем это держится.

Стадия живёт в своём репозитории и разговаривает с контуром через порты. Здесь
проверяется НАША сторона: что обещанное портом действительно есть и что подмена
в тесте до стадии доходит.
"""

import pytest

import developer_bridge
import forge
from poh_developer import ports
from shared import howtodemo, issue_blocks, memory, repowise, sentry_setup


@pytest.fixture
def installed():
    developer_bridge.install()
    yield
    developer_bridge.install()   # вернуть боевые реализации следующим тестам


def test_every_port_is_wired(installed):
    """Незаданный порт отказывает RuntimeError'ом на первом же живом прогоне."""
    for get in (ports.github, ports.issue_blocks, ports.repowise,
                ports.memory, ports.telemetry):
        assert get() is not None


@pytest.mark.parametrize("proto, get", [
    (ports.GitHubPort, ports.github),
    (ports.IssueBlocksPort, ports.issue_blocks),
    (ports.RepowisePort, ports.repowise),
    (ports.MemoryPort, ports.memory),
    (ports.TelemetryPort, ports.telemetry),
])
def test_the_adapter_answers_everything_the_port_promises(installed, proto, get):
    """Метод, объявленный портом и не найденный у адаптера, — обещание, которое
    стадия обнаружит невыполненным на живом прогоне, посреди чужого стека.

    Сверка со ВСЕМ протоколом, а не со списком: порт растёт в соседнем
    репозитории, и список посередине отстал бы молча.
    """
    promised = {n for n in dir(proto) if not n.startswith("_")}
    promised |= set(getattr(proto, "__annotations__", {}))
    adapter = get()

    missing = [n for n in sorted(promised) if not hasattr(adapter, n)]

    assert missing == []


def test_the_adapter_asks_the_module_at_the_call(installed, monkeypatch):
    """Адаптер делегирует МОДУЛЮ, а не связывается с функцией при сборке.

    Иначе три десятка тестовых файлов подменяли бы `forge.post_comment`, а
    стадия звала бы ту, что была на старте, — подмена никуда не подключена, и
    тест зелёный на пути, который не работает.
    """
    seen: list = []
    monkeypatch.setattr(forge, "post_comment",
                        lambda repo, n, body: seen.append((repo, n, body)))

    ports.github().post_comment("o/r", 42, "текст")

    assert seen == [("o/r", 42, "текст")]


def test_the_clone_carries_the_branch(installed, monkeypatch):
    """Круг правок работает поверх ветки PR: потерянная ветка положила бы
    правки не на то, что видел ревьюер (живой прогон #19)."""
    import activities

    seen: list = []
    monkeypatch.setattr(activities, "_clone_repo",
                        lambda repo, dest, branch: seen.append(branch))

    ports.github().clone_repo("o/r", "/tmp/x", "fix/pr-7")

    assert seen == ["fix/pr-7"]


def test_the_scenario_comes_by_the_contours_own_rule(installed):
    """Сценарий приёмки читается правилом контура: у размеченного блока
    приоритет над одноимённым разделом тела. Стадия этого правила не знает."""
    body = ("## HowToDemo\nстарый раздел\n\n"
            + issue_blocks.write("", "harness:howtodemo", "новый блок"))

    assert ports.issue_blocks().howtodemo_block(body) == howtodemo.read(body)
    assert "новый блок" in ports.issue_blocks().howtodemo_block(body)


def test_optional_layers_reach_their_real_modules(installed):
    """Индекс кода и слой памяти необязательны, и решает это КОНТУР: стадия
    спрашивает порт и идёт путём без них, если тот сказал «выключено»."""
    assert ports.repowise().enabled() is repowise.enabled()
    assert ports.memory().enabled() is memory.enabled()
    assert ports.repowise().DEVELOP == repowise.DEVELOP
    assert ports.memory().DEVELOP == memory.DEVELOP


def test_a_lost_finding_becomes_an_event(installed, monkeypatch):
    """Находка агента, не доехавшая до тела задачи, обязана стать событием, а
    не строкой `warning`: порог `event_level=ERROR` warning'и не пропускает."""
    seen: list = []
    monkeypatch.setattr(sentry_setup, "capture_followups_failure",
                        lambda issue, exc_type, message: seen.append(exc_type))

    ports.telemetry().capture_followups_failure(object(), "ValueError", "текст")

    assert seen == ["ValueError"]
