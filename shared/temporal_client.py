"""Единая точка подключения к Temporal для worker, webhook и скриптов.

Конфигурация из окружения:
  TEMPORAL_ADDRESS    host:port (по умолчанию localhost:7233)
  TEMPORAL_NAMESPACE  namespace (по умолчанию default)
  TEMPORAL_TLS        "1"/"true"/"yes" — включить TLS (по умолчанию выкл).

Централизованный кластер в доверенной/allowlist-сети работает по plain gRPC.
Включай TEMPORAL_TLS, когда кластер поддерживает TLS: тогда трафик workflow и
activity, несущий содержимое Issue, шифруется в транзите, а сервер
аутентифицируется по сертификату.
"""

import os

from temporalio.client import Client


def _tls_enabled() -> bool:
    return os.environ.get("TEMPORAL_TLS", "").strip().lower() in ("1", "true", "yes")


async def connect_temporal() -> Client:
    """Подключиться к Temporal по конфигурации из окружения."""
    return await Client.connect(
        os.environ.get("TEMPORAL_ADDRESS", "localhost:7233"),
        namespace=os.environ.get("TEMPORAL_NAMESPACE", "default"),
        tls=_tls_enabled(),
    )
