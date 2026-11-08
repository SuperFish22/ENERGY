"""Телеграм-бот ENERGY. Работает на ОТДЕЛЬНОМ сервере и общается с сайтом только через его API.

Что умеет:
  • раз в 15 секунд забирает новые заявки с сайта и шлёт их в чат организаторов (LEADS_CHAT_ID)
    с кнопками «Связались / Зачислен / Отказ» — нажатие меняет статус на сайте;
  • /start — кнопки, открывающие сайт прямо в Telegram (кабинет, игротека, база, конструкторы);
  • /igra — случайная игра из открытой игротеки (/igra кричалки — из раздела);
  • /chatid — показать id чата.

Настройки — в файле .env рядом с ботом (см. .env.example). Запуск: python bot.py
"""
import asyncio
import logging
import os
from html import escape
from pathlib import Path

import aiohttp
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, MenuButtonWebApp, Message,
                           WebAppInfo)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).with_name(".env"))
except ImportError:
    pass

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
SITE_URL = os.getenv("SITE_URL", "").rstrip("/")  # https://energy-academy.ru
BOT_API_TOKEN = os.getenv("BOT_API_TOKEN", "")  # такой же, как в .env сайта
LEADS_CHAT_ID = os.getenv("LEADS_CHAT_ID", "")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "15"))

STATUSES = {"contacted": "Связались", "enrolled": "Зачислен", "rejected": "Отказ"}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("energy-bot")
dp = Dispatcher()
http: aiohttp.ClientSession | None = None


# ---------------------------------------------------------------- связь с сайтом

class SiteError(Exception):
    pass


async def api(method: str, path: str, **kwargs) -> dict:
    """Запрос к API сайта с ключом бота."""
    assert http is not None
    url = f"{SITE_URL}/api/bot{path}"
    headers = {"Authorization": f"Bearer {BOT_API_TOKEN}"}
    try:
        async with http.request(method, url, headers=headers, timeout=aiohttp.ClientTimeout(total=15), **kwargs) as r:
            if r.status == 401:
                raise SiteError("Сайт не принял ключ: проверьте, что BOT_API_TOKEN одинаковый у сайта и бота")
            if r.status == 404:
                raise SiteError("API бота на сайте выключено: задайте BOT_API_TOKEN в .env сайта")
            if r.status >= 400:
                raise SiteError(f"Сайт ответил {r.status}")
            return await r.json()
    except aiohttp.ClientError as e:
        raise SiteError(f"Нет связи с сайтом: {e}") from e


def markup(data: dict | None) -> InlineKeyboardMarkup | None:
    return InlineKeyboardMarkup.model_validate(data) if data else None


def webapp(path: str) -> WebAppInfo:
    return WebAppInfo(url=f"{SITE_URL}/app?to={path}")


# ---------------------------------------------------------------- команды

@dp.message(CommandStart())
async def start(message: Message):
    kb = None
    if SITE_URL.startswith("https://"):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡️ Личный кабинет", web_app=webapp("/cabinet"))],
            [InlineKeyboardButton(text="🎲 Игротека", web_app=webapp("/igroteka")),
             InlineKeyboardButton(text="📚 База знаний", web_app=webapp("/baza"))],
            [InlineKeyboardButton(text="🛠 Конструкторы", web_app=webapp("/konstruktor"))],
        ])
    await message.answer(
        "Привет! Это бот школы вожатых ENERGY ⚡️\n\n"
        "Здесь будут напоминания о занятиях и новости потока. "
        "Записаться на обучение можно на сайте.\n\nENERGY. Дерзай!",
        reply_markup=kb,
    )


@dp.message(Command("igra"))
async def random_game(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    try:
        data = await api("GET", "/game", params={"section": parts[1] if len(parts) > 1 else ""})
    except SiteError as e:
        log.warning("igra: %s", e)
        return await message.answer("Не получилось достать игру — сайт сейчас не отвечает. Попробуйте позже.")
    g = data.get("game")
    if not g:
        return await message.answer("Такой игры не нашлось. Попробуйте /igra или /igra знакомство")
    text = f"🎲 <b>{escape(g['title'])}</b>\n<i>{escape(g['section'] or '')}</i>\n\n{escape(g['text'])}"
    if g.get("url", "").startswith("https://"):
        text += f"\n\n<a href=\"{escape(g['url'])}\">Полностью на сайте</a>"
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
    if status not in STATUSES:
        return await cb.answer("Непонятный статус")
    try:
        res = await api("POST", f"/leads/{lead_id}/status",
                        json={"status": status, "tg_id": cb.from_user.id, "by": cb.from_user.full_name})
    except SiteError as e:
        log.warning("lead status: %s", e)
        return await cb.answer("Сайт сейчас не отвечает, попробуйте через минуту", show_alert=True)
    if not res.get("ok"):
        return await cb.answer(res.get("error", "Не получилось"), show_alert=True)
    await cb.message.edit_text(res["text"], parse_mode="HTML", reply_markup=markup(res.get("reply_markup")))
    await cb.answer("Готово")


# ---------------------------------------------------------------- заявки с сайта

async def poll_leads(bot: Bot):
    """Каждые POLL_SECONDS секунд забирает новые заявки и отправляет их в чат организаторов."""
    if not LEADS_CHAT_ID:
        log.warning("LEADS_CHAT_ID не задан — заявки в чат отправляться не будут")
        return
    warned = False
    while True:
        try:
            data = await api("GET", "/leads/pending")
            warned = False
            for lead in data.get("leads", []):
                await bot.send_message(LEADS_CHAT_ID, lead["text"], parse_mode="HTML",
                                       reply_markup=markup(lead.get("reply_markup")))
                await api("POST", f"/leads/{lead['id']}/notified")
                log.info("Заявка #%s отправлена в чат", lead["id"])
        except SiteError as e:
            if not warned:  # не засоряем лог одной и той же ошибкой
                log.warning("Заявки: %s", e)
                warned = True
        except Exception:
            log.exception("Заявки: не получилось отправить в Telegram")
        await asyncio.sleep(POLL_SECONDS)


async def main():
    global http
    missing = [n for n, v in [("BOT_TOKEN", BOT_TOKEN), ("SITE_URL", SITE_URL), ("BOT_API_TOKEN", BOT_API_TOKEN)] if not v]
    if missing:
        raise SystemExit("Впишите в .env бота: " + ", ".join(missing))
    http = aiohttp.ClientSession()
    bot = Bot(BOT_TOKEN)
    try:
        try:
            await api("GET", "/health")
            log.info("Связь с сайтом %s есть", SITE_URL)
        except SiteError as e:
            log.error("%s — бот запустится, но заявки и /igra не заработают, пока это не исправить", e)
        if SITE_URL.startswith("https://"):
            # кнопка «Меню» рядом с полем ввода открывает сайт как приложение внутри Telegram
            await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="ENERGY", web_app=webapp("/cabinet")))
        asyncio.create_task(poll_leads(bot))
        await dp.start_polling(bot)
    finally:
        await http.close()


if __name__ == "__main__":
    asyncio.run(main())
