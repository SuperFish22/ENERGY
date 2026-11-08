"""API для Telegram-бота, который работает на другом сервере.

Бот не видит базу сайта, поэтому всё делает через эти адреса. Защита — ключ BOT_API_TOKEN
в заголовке «Authorization: Bearer <ключ>» (одинаковый в .env сайта и бота).

  GET  /api/bot/health                    — проверить связь и ключ
  GET  /api/bot/leads/pending             — новые заявки, которые ещё не отправлены в чат
  POST /api/bot/leads/{id}/notified       — бот отправил заявку в чат
  POST /api/bot/leads/{id}/status         — нажата кнопка «Связались / Зачислен / Отказ»
  GET  /api/bot/game?section=…            — случайная открытая игра для /igra
"""
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import config
from ..db import LEAD_STATUSES, Game, Lead, User, now
from ..permissions import has_perm
from ..telegram import lead_keyboard, lead_text
from ..utils import plain_excerpt
from ..web import get_db

router = APIRouter(prefix="/api/bot")


def bot_auth(request: Request) -> None:
    if not config.BOT_API_TOKEN:
        raise HTTPException(404)  # API выключено, пока не задан ключ
    sent = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
    if not secrets.compare_digest(sent, config.BOT_API_TOKEN):
        raise HTTPException(401, "Неверный ключ бота")


def _lead_payload(lead: Lead) -> dict:
    text = lead_text(lead)
    if lead.status != "new":
        text += f"\n\n<b>Статус:</b> {LEAD_STATUSES.get(lead.status, lead.status)}"
    return {"id": lead.id, "text": text, "reply_markup": lead_keyboard(lead.id)}


@router.get("/health", dependencies=[Depends(bot_auth)])
def health():
    return {"ok": True, "site": config.SITE_URL}


@router.get("/leads/pending", dependencies=[Depends(bot_auth)])
def pending_leads(db: Session = Depends(get_db)):
    # только свежие: чтобы при первом включении бота в чат не высыпались все старые заявки
    since = now() - timedelta(days=2)
    leads = (db.query(Lead).filter(Lead.notified_at.is_(None), Lead.created_at >= since)
             .order_by(Lead.id).limit(20).all())
    return {"leads": [_lead_payload(l) for l in leads]}


@router.post("/leads/{lead_id}/notified", dependencies=[Depends(bot_auth)])
def lead_notified(lead_id: int, db: Session = Depends(get_db)):
    lead = db.get(Lead, lead_id)
    if lead is None:
        raise HTTPException(404)
    lead.notified_at = now()
    db.commit()
    return {"ok": True}


@router.post("/leads/{lead_id}/status", dependencies=[Depends(bot_auth)])
async def lead_status(lead_id: int, request: Request, db: Session = Depends(get_db)):
    data = await request.json()
    status = data.get("status")
    try:
        tg_id = int(data.get("tg_id"))
    except (TypeError, ValueError):
        raise HTTPException(400, "Нет tg_id")
    by = str(data.get("by") or "")[:100]
    if status not in LEAD_STATUSES:
        raise HTTPException(400, "Непонятный статус")
    who = db.query(User).filter(User.tg_id == tg_id).first()
    allowed = tg_id in config.SUPERADMIN_IDS or (who is not None and has_perm(who, "leads.manage"))
    if not allowed:
        return {"ok": False, "error": "Менять статус могут те, у кого есть право «Обрабатывать заявки». "
                                      "Сначала войдите на сайт через Telegram."}
    lead = db.get(Lead, lead_id)
    if lead is None:
        return {"ok": False, "error": "Заявка не найдена"}
    lead.status = status
    lead.admin_note = ((lead.admin_note or "") + f"\n{LEAD_STATUSES[status]} — {by}").strip()
    db.commit()
    payload = _lead_payload(lead)
    payload["text"] = lead_text(lead) + f"\n\n<b>Статус:</b> {LEAD_STATUSES[status]} ({by})"
    return {"ok": True, **payload}


@router.get("/game", dependencies=[Depends(bot_auth)])
def random_game(section: str = "", db: Session = Depends(get_db)):
    q = db.query(Game).filter(Game.status == "published", Game.is_public.is_(True))
    if section.strip():
        q = q.filter(Game.section.ilike(f"%{section.strip()}%"))
    g = q.order_by(func.random()).first()
    if g is None:
        return {"game": None}
    return {"game": {"title": g.title, "section": g.section, "text": plain_excerpt(g.body, 700),
                     "url": f"{config.SITE_URL}/igroteka/{g.slug}"}}
