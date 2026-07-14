# tests/test_consolidate_launcher.py
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import consolidate


def test_launcher_starts_workflow(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["consolidate", "--repo", "o/r"])
    mock_client = AsyncMock()
    mock_client.execute_workflow = AsyncMock(return_value="http://pr/1")
    with patch("consolidate.Client.connect", AsyncMock(return_value=mock_client)):
        asyncio.run(consolidate.main())
    mock_client.execute_workflow.assert_awaited_once()
