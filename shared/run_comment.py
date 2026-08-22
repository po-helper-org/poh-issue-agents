"""Единый слой управления комментариями прогона: плейсхолдер → правка → финал.

Принцип «одно сообщение на задачу»: как только работа взята — сразу комментарий
с RunID («взял в работу»), затем по ходу работы он обновляется на месте, а по
завершении публикуется финальный результат и плейсхолдер удаляется.

Гибридная стратегия:
- Промежуточные статусы — правка на месте (нет уведомления, но это и не нужно)
- Финальный результат — новый комментарий + удаление плейсхолдера (есть пинг)
- Порядок: СНАЧАЛА опубликовать результат, ПОТОМ удалить плейсхолдер
- Короткие операции плейсхолдер не заводят вовсе

Почему не только правка: GitHub не шлёт уведомление о правке комментария.
Человек, читающий Issue с телефона, узнает о результате только если вернётся
и проверит. Уведомление о новом комментарии — единственный пинг о готовности.

Idempotency: повторная доставка того же комментария (ретрай GitHub) упирается
в тот же workflow id — плейсхолдер не должен задваиваться.
"""

from typing import Protocol
import asyncio
import logging
import requests

from shared.agent_comment import sign
from worker.github_client import _auth_headers, _dry_run

logger = logging.getLogger(__name__)


class CommentBackend(Protocol):
    """Интерфейс для работы с комментариями — нужен для тестов."""

    def post_comment(self, repo: str, issue_number: int, body: str) -> int:
        """Публикует комментарий и возвращает его ID."""

    def update_comment(self, repo: str, comment_id: int, body: str) -> None:
        """Правит существующий комментарий."""

    def delete_comment(self, repo: str, comment_id: int) -> None:
        """Удаляет комментарий."""


class RealCommentBackend:
    """Реальный backend через GitHub API."""

    def post_comment(self, repo: str, issue_number: int, body: str) -> int:
        """Публикует подписанный комментарий и возвращает его ID."""
        url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
        headers = _auth_headers(repo)
        body = sign(body)
        
        if _dry_run():
            logger.info("[DRY_RUN] comment %s#%s: %s", repo, issue_number, body[:200])
            return 0  # В dry run возвращаем фиктивный ID
        
        resp = requests.post(url, headers=headers, json={"body": body}, timeout=30)
        resp.raise_for_status()
        return resp.json()["id"]

    def update_comment(self, repo: str, comment_id: int, body: str) -> None:
        """Правит подписанный комментарий."""
        url = f"https://api.github.com/repos/{repo}/issues/comments/{comment_id}"
        headers = _auth_headers(repo)
        body = sign(body)
        
        if _dry_run():
            logger.info("[DRY_RUN] update comment %s#%d: %s", repo, comment_id, body[:200])
            return
        
        resp = requests.patch(url, headers=headers, json={"body": body}, timeout=30)
        resp.raise_for_status()

    def delete_comment(self, repo: str, comment_id: int) -> None:
        """Удаляет комментарий. 404 не считаем ошибкой — уже удалён."""
        url = f"https://api.github.com/repos/{repo}/issues/comments/{comment_id}"
        headers = _auth_headers(repo)
        
        if _dry_run():
            logger.info("[DRY_RUN] delete comment %s#%d", repo, comment_id)
            return
        
        resp = requests.delete(url, headers=headers, timeout=30)
        if resp.status_code == 404:
            return  # Уже удалён — нормально
        resp.raise_for_status()


# Глобальный backend, можно подменить в тестах
_backend: CommentBackend = RealCommentBackend()


def set_backend(backend: CommentBackend) -> None:
    """Подменяет backend (нужно для тестов)."""
    global _backend
    _backend = backend


async def open_run_comment(
    repo: str,
    issue_number: int,
    run_id: str,
    message: str,
    *,
    skip_placeholder: bool = False
) -> int | None:
    """Открывает комментарий прогона: publishes placeholder with RunID.

    Args:
        repo: Репозиторий (owner/name)
        issue_number: Номер Issue
        run_id: RunID Temporal-прогона
        message: Текст сообщения о начале работы
        skip_placeholder: Если True, плейсхолдер не создаётся (короткие операции)

    Returns:
        ID созданного комментария или None если skip_placeholder=True

    Пример:
        >>> comment_id = await open_run_comment(
        ...     "owner/repo", 123, "abc123",
        ...     "🔍 Взял `/analyze` в работу — запускаю анализ."
        ... )
        >>> # Позже:
        >>> await update_run_comment("owner/repo", comment_id, "🔄 Анализирую...")
    """
    if skip_placeholder:
        return None
    
    text = f"{message}\n\n**RunID:** `{run_id}`"
    comment_id = await asyncio.to_thread(
        _backend.post_comment, repo, issue_number, text
    )
    logger.info("Opened run comment %s#%d: %s", repo, comment_id, run_id)
    return comment_id


async def update_run_comment(
    repo: str,
    comment_id: int | None,
    message: str
) -> None:
    """Обновляет комментарий прогона на месте (промежуточный статус).

    Args:
        repo: Репозиторий (owner/name)
        comment_id: ID комментария, None → ничего не делаем
        message: Новый текст сообщения

    Промежуточные статусы обновляются правкой на месте — нет уведомления,
    но это и не нужно для прогресса. Финальный результат публикуется
    через finish_run_comment().
    """
    if comment_id is None:
        return
    
    await asyncio.to_thread(
        _backend.update_comment, repo, comment_id, message
    )
    logger.debug("Updated run comment %s#%d", repo, comment_id)


async def finish_run_comment(
    repo: str,
    issue_number: int,
    placeholder_id: int | None,
    result_message: str,
    run_id: str
) -> None:
    """Финализирует комментарий прогона: публикует результат, удаляет плейсхолдер.

    Строгий порядок:
    1. СНАЧАЛА публикуем финальный результат (новый комментарий)
    2. ПОТОМ удаляем плейсхолдер

    Обратный порядок открывает окно, где у человека нет ни ожидания, ни результата.
    При таком порядке худший исход — плейсхолдер остался висеть рядом с ответом.

    Args:
        repo: Репозиторий (owner/name)
        issue_number: Номер Issue
        placeholder_id: ID плейсхолдера, None → только публикуем результат
        result_message: Финальное сообщение с результатом
        run_id: RunID для дублирования в финальном сообщении

    RunID дублируем в финальном сообщении — иначе он умирает вместе с плейсхолдером.
    """
    # Сначала публикуем результат
    text = f"{result_message}\n\n**RunID:** `{run_id}`"
    await asyncio.to_thread(
        _backend.post_comment, repo, issue_number, text
    )
    logger.info("Published final result for %s#%s", repo, issue_number)
    
    # Потом удаляем плейсхолдер, если он был
    if placeholder_id is not None:
        await asyncio.to_thread(
            _backend.delete_comment, repo, placeholder_id
        )
        logger.info("Deleted placeholder comment %s#%d", repo, placeholder_id)
