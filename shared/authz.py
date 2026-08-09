"""Кто вправе запускать дорогие стадии.

Метка ставится в два тапа, а запускает прогон на десятки минут `claude -p` и
чужие токены. Право поставить метку есть у любого с доступом к репозиторию,
поэтому решение принимается по АВТОРУ СОБЫТИЯ (`sender.login`), а не по факту
наличия метки: метку мог повесить кто угодно.

AGENT_TRIGGER_ALLOWLIST — comma-separated GitHub-логины. Пусто/не задан =
разрешено всем: так вёл себя сервис до появления проверки, и включение
allowlist остаётся осознанным действием оператора, а не сюрпризом после
обновления.

Дешёвые пути (issues.opened, обычные комментарии в цикле уточнений) сюда не
попадают: триаж должен работать для всех, иначе Issue от постороннего просто
не обработается.
"""

import os


def trigger_allowlist() -> list[str]:
    raw = os.environ.get("AGENT_TRIGGER_ALLOWLIST", "")
    return [entry.strip() for entry in raw.split(",") if entry.strip()]


def may_trigger(login: str | None, allowlist: list[str]) -> bool:
    """True, если этому логину разрешено запускать дорогие стадии."""
    if not allowlist:
        return True  # не настроено — прежнее поведение
    return (login or "").strip().lower() in {entry.lower() for entry in allowlist}
