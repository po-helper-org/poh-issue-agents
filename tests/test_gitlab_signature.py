"""Подлинность доставки GitLab: два режима, и ни один не угадывается."""
import base64
import hashlib
import hmac

import pytest

from shared.gitlab_signature import (
    MODE_HMAC, MODE_TOKEN, SignatureError, verify, verify_hmac, verify_token,
)

SECRET_RAW = "s3cret-key"
SECRET_WHSEC = "whsec_" + base64.b64encode(b"binary-key").decode()
BODY = b'{"object_kind":"issue"}'
NOW = 1_700_000_000


def sign(body, secret_key: bytes, wid="msg-1", ts=NOW):
    msg = f"{wid}.{ts}.".encode() + body
    return base64.b64encode(hmac.new(secret_key, msg, hashlib.sha256).digest()).decode()


def headers(sig, wid="msg-1", ts=NOW):
    return {"webhook-id": wid, "webhook-timestamp": str(ts), "webhook-signature": f"v1,{sig}"}


# --- HMAC ---

def test_верная_подпись_проходит():
    verify_hmac(BODY, headers(sign(BODY, SECRET_RAW.encode())), SECRET_RAW, now=NOW)


def test_ключ_whsec_декодируется_из_base64():
    verify_hmac(BODY, headers(sign(BODY, b"binary-key")), SECRET_WHSEC, now=NOW)


def test_подделанное_тело_не_проходит():
    sig = headers(sign(BODY, SECRET_RAW.encode()))
    with pytest.raises(SignatureError, match="ни одна подпись"):
        verify_hmac(b'{"object_kind":"evil"}', sig, SECRET_RAW, now=NOW)


def test_чужой_секрет_не_проходит():
    with pytest.raises(SignatureError):
        verify_hmac(BODY, headers(sign(BODY, b"wrong")), SECRET_RAW, now=NOW)


def test_подпись_привязана_к_id_и_времени():
    """Подпись, снятая с другой доставки, не годится для этой."""
    sig = sign(BODY, SECRET_RAW.encode(), wid="msg-1")
    with pytest.raises(SignatureError):
        verify_hmac(BODY, headers(sig, wid="msg-2"), SECRET_RAW, now=NOW)


def test_старая_доставка_отвергается():
    sig = headers(sign(BODY, SECRET_RAW.encode(), ts=NOW - 4000), ts=NOW - 4000)
    with pytest.raises(SignatureError, match="старше допуска"):
        verify_hmac(BODY, sig, SECRET_RAW, now=NOW)


def test_доставка_из_будущего_тоже_отвергается():
    sig = headers(sign(BODY, SECRET_RAW.encode(), ts=NOW + 4000), ts=NOW + 4000)
    with pytest.raises(SignatureError, match="старше допуска"):
        verify_hmac(BODY, sig, SECRET_RAW, now=NOW)


def test_список_подписей_при_ротации_ключа():
    """Во время ротации GitLab шлёт две подписи через пробел."""
    good = sign(BODY, SECRET_RAW.encode())
    h = headers(good)
    h["webhook-signature"] = f"v1,{base64.b64encode(b'old').decode()} v1,{good}"
    verify_hmac(BODY, h, SECRET_RAW, now=NOW)


def test_нет_заголовков_подписи():
    with pytest.raises(SignatureError, match="нет заголовков"):
        verify_hmac(BODY, {}, SECRET_RAW, now=NOW)


def test_нечисловое_время():
    h = headers(sign(BODY, SECRET_RAW.encode()))
    h["webhook-timestamp"] = "вчера"
    with pytest.raises(SignatureError, match="не число"):
        verify_hmac(BODY, h, SECRET_RAW, now=NOW)


def test_чужая_версия_подписи_игнорируется():
    good = sign(BODY, SECRET_RAW.encode())
    h = headers(good)
    h["webhook-signature"] = f"v2,{good}"
    with pytest.raises(SignatureError):
        verify_hmac(BODY, h, SECRET_RAW, now=NOW)


# --- plain token ---

def test_токен_совпал():
    verify_token({"X-Gitlab-Token": SECRET_RAW}, SECRET_RAW)


def test_токен_не_совпал():
    with pytest.raises(SignatureError, match="не совпал"):
        verify_token({"X-Gitlab-Token": "чужой"}, SECRET_RAW)


def test_токена_нет():
    with pytest.raises(SignatureError, match="нет заголовка"):
        verify_token({}, SECRET_RAW)


# --- диспетчер ---

def test_режим_не_угадывается_а_задаётся():
    """Доставка с plain-токеном не проходит, когда включён режим HMAC."""
    with pytest.raises(SignatureError):
        verify(BODY, {"X-Gitlab-Token": SECRET_RAW}, SECRET_RAW, MODE_HMAC, now=NOW)


def test_пустой_секрет_блокирует_оба_режима():
    for mode in (MODE_HMAC, MODE_TOKEN):
        with pytest.raises(SignatureError, match="секрет вебхука не задан"):
            verify(BODY, {}, "", mode)


def test_неизвестный_режим():
    with pytest.raises(SignatureError, match="неизвестный режим"):
        verify(BODY, {}, SECRET_RAW, "магия")
