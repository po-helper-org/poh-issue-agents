"""Три подтверждённых дефекта из разбора бэклога 3 сентября.

- #95: подтверждённый дубликат не закрывался на GitHub — фаза `cancelled`,
  а Issue висит открытым.
- #96: `duplicate_check` не смотрел состояние оригинала и мог объявить
  задачу дубликатом закрытой.
- #291: лимит частоты провайдера (429) классифицировался как неисправимый
  отказ и убивал сорокапятиминутный анализ.
"""

import activities as a
from shared.errors import RateLimited
from shared.workflow_types import IssueInput


def _issue() -> IssueInput:
    return IssueInput(repo="o/r", issue_number=7, title="t", body="b",
                      author_login="u", author_type="User", interactive=True)


def test_confirming_a_duplicate_closes_the_issue(monkeypatch):
    """Фазы `cancelled` мало: задача остаётся в списке открытых (#95)."""
    closed: list = []
    posted: list = []
    monkeypatch.setattr(a.github_client, "close_issue",
                        lambda repo, n: closed.append(n))
    monkeypatch.setattr(a.github_client, "post_comment",
                        lambda repo, n, body: posted.append(body))
    monkeypatch.setattr(a.github_client, "add_label", lambda repo, n, label: None)

    a.close_as_duplicate(_issue(), 3)

    assert closed == [7]
    assert "#3" in posted[0], "человеку нужна ссылка на оригинал"


def test_a_closed_original_is_not_offered_as_a_duplicate(monkeypatch):
    """Дубликат ЗАКРЫТОЙ задачи — не повод отменять новую (#96).

    Закрытая задача могла быть отклонена, устареть или быть решена иначе.
    Отменить по ней новую значит молча потерять запрос.
    """
    monkeypatch.setattr(a.github_client, "search_candidates", lambda repo, title: [
        {"number": 3, "state": "closed", "title": "старая", "body": "", "_kind": "issue"},
    ])
    called: list = []
    monkeypatch.setattr(a.llm, "extract",
                        lambda *args, **kwargs: called.append(1))

    result = a.duplicate_check(_issue())

    assert result.decision == "none"
    assert called == [], "модель звать не за чем — кандидатов не осталось"


def test_an_open_original_is_still_checked(monkeypatch):
    """Отсев по состоянию не должен выключить проверку целиком."""
    monkeypatch.setattr(a.github_client, "search_candidates", lambda repo, title: [
        {"number": 3, "state": "open", "title": "живая", "body": "", "_kind": "issue"},
    ])
    seen: list = []

    class _Extraction:
        candidates: list = []

    monkeypatch.setattr(a.llm, "extract",
                        lambda *args, **kwargs: seen.append(1) or _Extraction())

    a.duplicate_check(_issue())

    assert seen == [1], "открытого кандидата обязаны проверить"


def test_a_rate_limit_is_not_the_stages_own_failure(monkeypatch, tmp_path):
    """429 — не отказ стадии, а занятость провайдера (#291).

    `RuntimeError` объявлен неретраебельным намеренно: прогон стадии
    недетерминирован и стоит денег. Но лимит частоты к качеству прогона
    отношения не имеет — повтор по нему обязан быть, иначе сорок пять минут
    работы списываются из-за чужой очереди.
    """
    class _Done:
        returncode = 1
        stdout = "API Error: Request rejected (429)\n[1302][Rate limit reached for requests]"
        stderr = ""

    monkeypatch.setenv("ZAI_API_KEY", "k")
    monkeypatch.setenv("ZAI_BASE_URL", "https://example.invalid")
    monkeypatch.setattr(a.subprocess, "run", lambda *args, **kwargs: _Done())

    try:
        a._run_claude("/stage", cwd=str(tmp_path), mcp_config=None)
    except RateLimited:
        pass
    except RuntimeError as exc:  # noqa: BLE001
        raise AssertionError(
            f"лимит частоты снова объявлен неисправимым отказом: {exc}") from exc
    else:
        raise AssertionError("ожидался отказ")


def test_an_ordinary_failure_stays_non_retryable(monkeypatch, tmp_path):
    """Обычный сбой стадии по-прежнему `RuntimeError`.

    Иначе послабление для лимита превратилось бы в повтор дорогого
    недетерминированного прогона на любом отказе.
    """
    class _Done:
        returncode = 1
        stdout = "TypeError: cannot read property of undefined"
        stderr = ""

    monkeypatch.setenv("ZAI_API_KEY", "k")
    monkeypatch.setenv("ZAI_BASE_URL", "https://example.invalid")
    monkeypatch.setattr(a.subprocess, "run", lambda *args, **kwargs: _Done())

    try:
        a._run_claude("/stage", cwd=str(tmp_path), mcp_config=None)
    except RateLimited as exc:  # noqa: BLE001
        raise AssertionError("обычный сбой принят за лимит частоты") from exc
    except RuntimeError:
        pass
    else:
        raise AssertionError("ожидался отказ")
