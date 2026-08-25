"""Клиент слоя саморефлексии: выключатель и деградация.

Главное свойство, которое здесь проверяется, — слой опционален. Выключенный он
не делает ни одного вызова, недоступный не роняет прогон.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from shared import memory


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("MEMORY_BASE_URL", raising=False)
    monkeypatch.delenv("MEMORY_BASE_TOKEN", raising=False)
    monkeypatch.delenv("MEMORY_BASE_TIMEOUT_SEC", raising=False)


class _Handler(BaseHTTPRequestHandler):
    calls: list = []
    rules_body = {"text": "\nПравила:\n- пункт\n", "ids": ["R-1"], "dropped": 0}
    status = 200

    def log_message(self, *a):        # тишина в выводе тестов
        pass

    def _reply(self, body):
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(type(self).status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        type(self).calls.append(("GET", self.path, dict(self.headers)))
        if self.path.startswith("/health"):
            self._reply({"status": "ok"})
        else:
            self._reply(type(self).rules_body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n).decode("utf-8")
        type(self).calls.append(("POST", self.path, json.loads(raw)))
        self._reply({"run_id": "r1", "path": "memory/episodes/x.md"})


@pytest.fixture
def server(monkeypatch):
    _Handler.calls = []
    _Handler.status = 200
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("MEMORY_BASE_URL", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setenv("MEMORY_BASE_TOKEN", "test-token")
    yield _Handler
    srv.shutdown()


# ───────────────────────── выключатель ─────────────────────────

def test_disabled_when_url_is_empty():
    assert not memory.enabled()


def test_token_without_url_does_not_enable(monkeypatch):
    """Адрес — единственный выключатель."""
    monkeypatch.setenv("MEMORY_BASE_TOKEN", "t")
    assert not memory.enabled()


def test_rules_returns_empty_when_disabled():
    r = memory.rules(memory.DEVELOP, "o/r")
    assert r.text == "" and r.ids == [] and not r


def test_put_episode_returns_false_when_disabled():
    assert memory.put_episode({"run_id": "r1"}) is False


def test_disabled_layer_makes_no_network_call(monkeypatch):
    """Пустой адрес — ни одного вызова, а не вызов на пустой хост."""
    called = []
    monkeypatch.setattr(memory.urllib.request, "urlopen",
                        lambda *a, **k: called.append(1))
    memory.rules(memory.DEVELOP)
    memory.put_episode({"run_id": "r"})
    assert called == []


# ───────────────────────── обычная работа ─────────────────────────

def test_rules_returns_block_and_ids(server):
    r = memory.rules(memory.DEVELOP, "po-helper-org/demo", "починить кнопку")
    assert r.text.startswith("\n")
    assert r.ids == ["R-1"]
    assert bool(r) is True


def test_rules_sends_bearer_token(server):
    memory.rules(memory.DEVELOP)
    _, _, headers = server.calls[0]
    assert headers.get("Authorization") == "Bearer test-token"


def test_rules_passes_role_and_repo(server):
    memory.rules(memory.REVIEW, "o/r")
    _, path, _ = server.calls[0]
    assert "agent=review" in path and "o%2Fr" in path


def test_long_query_is_truncated(server):
    """Постановка бывает длинной, а длинный URL ломает прокси."""
    memory.rules(memory.DEVELOP, query="я" * 5000)
    _, path, _ = server.calls[0]
    assert len(path) < 2000


def test_unknown_role_does_not_call(server):
    assert memory.rules("выдумка").text == ""
    assert server.calls == []


def test_put_episode_sends_payload(server):
    ok = memory.put_episode({"run_id": "r1", "repo": "o/r", "issue": 1,
                             "rules_injected": ["R-1"]})
    assert ok is True
    method, path, body = server.calls[0]
    assert (method, path) == ("POST", "/episodes")
    assert body["rules_injected"] == ["R-1"]


def test_put_episode_without_run_id_is_refused(server):
    assert memory.put_episode({"repo": "o/r"}) is False
    assert server.calls == []


def test_health_needs_no_token(server):
    assert memory.health() == {"status": "ok"}
    _, _, headers = server.calls[0]
    assert "Authorization" not in headers


# ───────────────────────── деградация ─────────────────────────

def test_rules_degrades_on_connection_error(monkeypatch):
    monkeypatch.setenv("MEMORY_BASE_URL", "http://127.0.0.1:1")   # никто не слушает
    r = memory.rules(memory.DEVELOP)
    assert r.text == "" and r.ids == []


def test_put_episode_never_raises_on_connection_error(monkeypatch):
    monkeypatch.setenv("MEMORY_BASE_URL", "http://127.0.0.1:1")
    assert memory.put_episode({"run_id": "r1"}) is False


def test_rules_degrades_on_http_error(server):
    server.status = 500
    assert memory.rules(memory.DEVELOP).text == ""


def test_rules_degrades_on_malformed_body(server, monkeypatch):
    server.rules_body = {"text": None, "ids": "не список"}
    r = memory.rules(memory.DEVELOP)
    assert r.text == "" and r.ids == []
    server.rules_body = {"text": "\nx\n", "ids": ["R-1"], "dropped": 0}


def test_broken_url_does_not_raise(monkeypatch):
    monkeypatch.setenv("MEMORY_BASE_URL", "не адрес вовсе")
    assert memory.rules(memory.DEVELOP).text == ""
    assert memory.put_episode({"run_id": "r"}) is False


def test_bad_timeout_value_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("MEMORY_BASE_TIMEOUT_SEC", "не число")
    assert memory.timeout_sec() == memory.DEFAULT_TIMEOUT_SEC
