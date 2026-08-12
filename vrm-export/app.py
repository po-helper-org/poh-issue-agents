#!/usr/bin/env python3
"""
app.py — веб-сервис. Один процесс = отчёт + ручной запуск + импорт из
Facebook + внутренний планировщик (APScheduler), потому что Render Cron
Job не может примонтировать постоянный диск — см. render.yaml.

Все страницы, кроме /healthz, закрыты HTTP Basic (BASIC_AUTH_USER/PASS).
Если логин/пароль не заданы — сервис намеренно отвечает 503, а не
открывает доступ: там телефоны и фото людей, значение по умолчанию
"без пароля" здесь недопустимо.
"""
import hmac
import logging
import threading

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask import Flask, Response, jsonify, request

from pipeline import config as config_module
from pipeline import importer, run, storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

app = Flask(__name__)
cfg = config_module.load()
store = storage.Storage(cfg.data_dir)

_run_lock = threading.Lock()
_run_state = {"in_progress": False, "last_summary": None}


def _safe_eq(a: str, b: str) -> bool:
    return bool(a) and bool(b) and hmac.compare_digest(a, b)


def require_basic_auth(view):
    def wrapped(*args, **kwargs):
        if not (cfg.basic_auth_user and cfg.basic_auth_pass):
            return Response("BASIC_AUTH_USER/BASIC_AUTH_PASS не заданы — доступ закрыт.", 503)
        auth = request.authorization
        if not auth or not (_safe_eq(auth.username, cfg.basic_auth_user)
                             and _safe_eq(auth.password, cfg.basic_auth_pass)):
            return Response("Требуется авторизация.", 401,
                             {"WWW-Authenticate": 'Basic realm="viet-rent-monitor"'})
        return view(*args, **kwargs)
    wrapped.__name__ = view.__name__
    return wrapped


def require_run_token(view):
    def wrapped(*args, **kwargs):
        if not cfg.run_token:
            return Response("RUN_TOKEN не задан — эндпоинт отключён.", 503)
        supplied = request.headers.get("X-Run-Token", "")
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            supplied = supplied or auth_header[len("Bearer "):]
        if not _safe_eq(supplied, cfg.run_token):
            return Response("Неверный или отсутствующий токен.", 403)
        return view(*args, **kwargs)
    wrapped.__name__ = view.__name__
    return wrapped


@app.get("/healthz")
def healthz():
    return {"status": "ok"}, 200


@app.get("/")
@require_basic_auth
def index():
    html = store.latest_report_html()
    if html is None:
        return Response(
            "Отчётов пока нет. Запустите первый прогон: POST /run с заголовком "
            "X-Run-Token, или дождитесь расписания.", 200, mimetype="text/plain; charset=utf-8")
    return Response(html, 200, mimetype="text/html; charset=utf-8")


@app.get("/archive")
@require_basic_auth
def archive():
    reports = store.list_reports()
    items = "\n".join(
        f'<li><a href="/archive/{fname}">{label}</a></li>' for fname, label in reports
    ) or "<li>Пока пусто.</li>"
    html = (
        "<!doctype html><meta charset=utf-8><title>Архив прогонов</title>"
        "<body style='font:15px system-ui;max-width:640px;margin:40px auto'>"
        f"<h1>Архив прогонов</h1><p><a href='/'>← последний отчёт</a></p><ul>{items}</ul></body>"
    )
    return Response(html, 200, mimetype="text/html; charset=utf-8")


@app.get("/archive/<path:filename>")
@require_basic_auth
def archive_file(filename):
    path = store.report_path(filename)
    if path is None:
        return Response("Не найдено.", 404)
    return Response(path.read_text(encoding="utf-8"), 200, mimetype="text/html; charset=utf-8")


def _run_job():
    if not _run_lock.acquire(blocking=False):
        log.info("Прогон уже идёт — новый запуск пропущен")
        return
    try:
        _run_state["in_progress"] = True
        summary = run.run_once(cfg)
        _run_state["last_summary"] = summary
    except Exception:
        log.exception("Прогон упал с необработанным исключением")
    finally:
        _run_state["in_progress"] = False
        _run_lock.release()


@app.post("/run")
@require_run_token
def trigger_run():
    if _run_state["in_progress"]:
        return jsonify(status="already_running"), 409
    threading.Thread(target=_run_job, daemon=True).start()
    return jsonify(status="started"), 202


@app.post("/import")
@require_run_token
def trigger_import():
    payload = request.get_json(silent=True)
    if not isinstance(payload, list):
        return jsonify(error="ожидается JSON-список [{text, url, photos}]"), 400
    result = importer.import_posts(store, payload)
    return jsonify(result), 200


def _start_scheduler():
    scheduler = BackgroundScheduler(timezone="UTC")
    trigger = CronTrigger.from_crontab(cfg.run_cron, timezone="UTC")
    scheduler.add_job(_run_job, trigger, id="daily_run", misfire_grace_time=3600, coalesce=True)
    scheduler.start()
    log.info("Планировщик запущен: RUN_CRON=%s (UTC)", cfg.run_cron)
    return scheduler


_scheduler = _start_scheduler()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
