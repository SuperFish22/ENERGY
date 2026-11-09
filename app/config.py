"""Настройки сайта. Всё берётся из переменных окружения / файла .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
load_dotenv(ROOT_DIR / ".env")


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _ids(name: str) -> set[int]:
    raw = os.getenv(name, "")
    return {int(x) for x in raw.replace(" ", "").split(",") if x.lstrip("-").isdigit()}


SITE_URL = os.getenv("SITE_URL", "http://localhost:8000").rstrip("/")
SITE_NAME = "Школа вожатых ENERGY"
SITE_CITY = os.getenv("SITE_CITY", "Москве")  # в предложном падеже: «в Москве»

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-please")
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{ROOT_DIR / 'data' / 'energy.db'}")

# Телеграм
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_USERNAME = os.getenv("BOT_USERNAME", "")  # без @, нужен для кнопки «Войти через Telegram»
LEADS_CHAT_ID = os.getenv("LEADS_CHAT_ID", "")  # чат/группа, куда падают заявки
SUPERADMIN_IDS = _ids("SUPERADMIN_IDS")
# Ключ, по которому бот с другого сервера ходит в API сайта (/api/bot/...).
# Если задан — сайт сам в Telegram не пишет, заявки забирает и отправляет бот.
BOT_API_TOKEN = os.getenv("BOT_API_TOKEN", "")  # tg id людей, которые всегда «Руководитель»

# Ссылки
VK_URL = os.getenv("VK_URL", "https://vk.com/planeta.energy")
TG_CHANNEL_URL = os.getenv("TG_CHANNEL_URL", "https://t.me/energy_getdrive")
INSTAGRAM_URL = os.getenv("INSTAGRAM_URL", "")  # пусто — кнопка Instagram не показывается
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "brio.laboratory@gmail.com")

# Вход без Телеграма — ТОЛЬКО для локальной разработки
DEV_LOGIN = _bool("DEV_LOGIN", False)
HTTPS_ONLY = SITE_URL.startswith("https://")
