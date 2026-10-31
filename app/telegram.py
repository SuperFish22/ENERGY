"""Проверка входа через Telegram и отправка уведомлений через Bot API (без лишних зависимостей)."""
import asyncio
import hashlib
import hmac
import json
import logging
import time
import urllib.request
from html import escape

from . import config
from .db import Lead

log = logging.getLogger("energy.telegram")


def verify_login(data: dict[str, str], max_age: int = 86400) -> bool:
    """https://core.telegram.org/widgets/login#checking-authorization"""
    if not config.BOT_TOKEN:
        return False
    received_hash = data.get("hash", "")
    check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()) if k != "hash")
    secret = hashlib.sha256(config.BOT_TOKEN.encode()).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received_hash):
        return False
    try:
        return time.time() - int(data.get("auth_date", "0")) < max_age
    except ValueError:
        return False


def _post(method: str, payload: dict) -> dict | None:
    if not config.BOT_TOKEN:
        return None
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{config.BOT_TOKEN}/{method}",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:  # уведомление не должно ронять сайт
        log.warning("Telegram %s failed: %s", method, e)
        return None


def lead_text(lead: Lead) -> str:
    rows = [
        f"⚡️ <b>Новая заявка #{lead.id}</b> — курс вожатых",
        "",
        f"👤 {escape(lead.full_name)}" + (f", {lead.age} лет" if lead.age else ""),
        f"📞 {escape(lead.phone)}",
    ]
    if lead.telegram:
        rows.append(f"✈️ {escape(lead.telegram)}")
    if lead.city:
        rows.append(f"🏙 {escape(lead.city)}")
    if lead.source:
        rows.append(f"🔎 Откуда узнал(а): {escape(lead.source)}")
    if lead.comment:
        rows.append(f"💬 {escape(lead.comment)}")
    return "\n".join(rows)


def lead_keyboard(lead_id: int) -> dict:
    rows = [[
        {"text": "✅ Связались", "callback_data": f"lead:{lead_id}:contacted"},
        {"text": "🎓 Зачислен", "callback_data": f"lead:{lead_id}:enrolled"},
        {"text": "✖️ Отказ", "callback_data": f"lead:{lead_id}:rejected"},
    ]]
    if config.SITE_URL.startswith("https://"):  # Telegram не принимает ссылки на localhost
        rows.append([{"text": "Открыть в админке", "url": f"{config.SITE_URL}/admin/leads?status=all#lead-{lead_id}"}])
    return {"inline_keyboard": rows}


async def notify_new_lead(lead: Lead) -> None:
    if not config.LEADS_CHAT_ID:
        return
    payload = {
        "chat_id": config.LEADS_CHAT_ID,
        "text": lead_text(lead),
        "parse_mode": "HTML",
        "reply_markup": lead_keyboard(lead.id),
    }
    await asyncio.to_thread(_post, "sendMessage", payload)


def verify_webapp(init_data: str, max_age: int = 86400) -> dict | None:
    """Проверка данных Telegram Mini App (WebApp.initData).
    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app"""
    from urllib.parse import parse_qsl
    if not config.BOT_TOKEN or not init_data:
        return None
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received = pairs.pop("hash", "")
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received):
        return None
    try:
        if time.time() - int(pairs.get("auth_date", "0")) > max_age:
            return None
        return json.loads(pairs.get("user", "{}"))
    except (ValueError, json.JSONDecodeError):
        return None
