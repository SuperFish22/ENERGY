"""Телеграм-бот ENERGY.

• Новые заявки с сайта приходят в чат LEADS_CHAT_ID с кнопками «Связались / Зачислен / Отказ».
  Нажатие кнопки меняет статус заявки на сайте.
• /start — приветствие и кнопка на сайт.
• /chatid — показать id текущего чата (чтобы вписать его в LEADS_CHAT_ID).

Запуск: python bot.py
"""
import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, Message,
                           WebAppInfo)

from app import config
from app.db import LEAD_STATUSES, Lead, SessionLocal, User, init_db
from app.permissions import has_perm
from app.telegram import lead_keyboard, lead_text

logging.basicConfig(level=logging.INFO)
dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: Message):
    kb = None
    if config.SITE_URL.startswith("https://"):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡️ Личный кабинет", web_app=WebAppInfo(url=f"{config.SITE_URL}/app?to=/cabinet"))],
            [InlineKeyboardButton(text="🎲 Игротека", web_app=WebAppInfo(url=f"{config.SITE_URL}/app?to=/igroteka")),
             InlineKeyboardButton(text="📚 База знаний", web_app=WebAppInfo(url=f"{config.SITE_URL}/app?to=/baza"))],
            [InlineKeyboardButton(text="🛠 Конструкторы", web_app=WebAppInfo(url=f"{config.SITE_URL}/app?to=/konstruktor"))],
        ])
    await message.answer(
        "Привет! Это бот школы вожатых ENERGY ⚡️\n\n"
        "Здесь будут напоминания о занятиях и новости потока. "
        "Записаться на обучение можно на сайте.\n\nENERGY. Дерзай!",
        reply_markup=kb,
    )


@dp.message(Command("igra"))
async def random_game(message: Message):
    """Случайная игра из открытой игротеки."""
    from sqlalchemy import func
    from app.db import Game
    from app.utils import plain_excerpt
    db = SessionLocal()
    try:
        q = db.query(Game).filter(Game.status == "published", Game.is_public.is_(True))
        arg = (message.text or "").split(maxsplit=1)
        if len(arg) > 1:
            q = q.filter(Game.section.ilike(f"%{arg[1].strip()}%"))
        g = q.order_by(func.random()).first()
    finally:
        db.close()
    if g is None:
        return await message.answer("Такой игры не нашлось. Попробуйте /igra или /igra знакомство")
    from html import escape
    text = f"🎲 <b>{escape(g.title)}</b>\n<i>{escape(g.section or '')}</i>\n\n{escape(plain_excerpt(g.body, 700))}"
    if config.SITE_URL.startswith("https://"):
        text += f"\n\n<a href=\"{config.SITE_URL}/igroteka/{g.slug}\">Полностью на сайте</a>"
    await message.answer(text, parse_mode="HTML", disable_web_page_preview=True)


@dp.message(Command("chatid"))
async def chat_id(message: Message):
    await message.answer(f"ID этого чата: <code>{message.chat.id}</code>", parse_mode="HTML")


@dp.callback_query(F.data.startswith("lead:"))
async def lead_status(cb: CallbackQuery):
    try:
        _, lead_id, status = cb.data.split(":")
        lead_id = int(lead_id)
    except ValueError:
        return await cb.answer("Непонятная кнопка")
    if status not in LEAD_STATUSES:
        return await cb.answer("Непонятный статус")

    db = SessionLocal()
    try:
        who = db.query(User).filter(User.tg_id == cb.from_user.id).first()
        allowed = cb.from_user.id in config.SUPERADMIN_IDS or (who is not None and has_perm(who, "leads.manage"))
        if not allowed:
            return await cb.answer("Менять статус могут те, у кого есть право «Обрабатывать заявки». "
                                   "Сначала войдите на сайт через Telegram.", show_alert=True)
        lead = db.get(Lead, lead_id)
        if lead is None:
            return await cb.answer("Заявка не найдена")
        lead.status = status
        by = cb.from_user.full_name
        lead.admin_note = ((lead.admin_note or "") + f"\n{LEAD_STATUSES[status]} — {by}").strip()
        db.commit()
        await cb.message.edit_text(
            lead_text(lead) + f"\n\n<b>Статус:</b> {LEAD_STATUSES[status]} ({by})",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup.model_validate(lead_keyboard(lead.id)),
        )
        await cb.answer("Готово")
    finally:
        db.close()


async def main():
    if not config.BOT_TOKEN:
        raise SystemExit("Впишите BOT_TOKEN в .env")
    init_db()
    bot = Bot(config.BOT_TOKEN)
    if config.SITE_URL.startswith("https://"):
        # кнопка «Меню» рядом с полем ввода открывает сайт как приложение внутри Telegram
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(
            text="ENERGY", web_app=WebAppInfo(url=f"{config.SITE_URL}/app?to=/cabinet")))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
