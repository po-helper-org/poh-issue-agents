"""Проверки подписи вебхука и initData мини-аппа."""

import json
from urllib.parse import quote_plus

import pytest

from tgbot.security import (
    InitDataError,
    build_init_data,
    check_webhook_secret,
    validate_init_data,
)

TOKEN = "123456:TEST-TOKEN"


def test_missing_secret_config_disables_check():
    assert check_webhook_secret(None, None) is True


def test_secret_must_match():
    assert check_webhook_secret("s3cret", "s3cret") is True
    assert check_webhook_secret("s3cret", "wrong") is False
    assert check_webhook_secret("s3cret", None) is False


def test_valid_init_data_round_trips():
    fields = {
        "auth_date": "1700000000",
        "query_id": "AAA",
        "user": json.dumps({"id": 7, "first_name": "Ада"}, ensure_ascii=False),
    }
    init_data = build_init_data(fields, TOKEN)

    parsed = validate_init_data(init_data, TOKEN, now=1700000010)

    assert json.loads(parsed["user"])["id"] == 7


def test_tampered_payload_is_rejected():
    init_data = build_init_data({"auth_date": "1700000000", "user": '{"id": 7}'}, TOKEN)
    tampered = init_data.replace(quote_plus('{"id": 7}'), quote_plus('{"id": 1}'))
    assert tampered != init_data, "подмена не сработала — тест бы прошёл впустую"

    with pytest.raises(InitDataError, match="подпись"):
        validate_init_data(tampered, TOKEN, now=1700000010)


def test_init_data_signed_by_another_bot_is_rejected():
    init_data = build_init_data({"auth_date": "1700000000"}, "other:TOKEN")

    with pytest.raises(InitDataError, match="подпись"):
        validate_init_data(init_data, TOKEN, now=1700000010)


def test_missing_hash_is_rejected():
    with pytest.raises(InitDataError, match="hash"):
        validate_init_data("auth_date=1700000000", TOKEN)


def test_stale_init_data_is_rejected():
    init_data = build_init_data({"auth_date": "1700000000"}, TOKEN)

    with pytest.raises(InitDataError, match="просрочена"):
        validate_init_data(init_data, TOKEN, max_age_seconds=60, now=1700000900)
