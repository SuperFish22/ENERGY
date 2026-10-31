"""Мелкие помощники: транслит для адресов, простая разметка текста, загрузка файлов."""
import re
import secrets
from html import escape
from pathlib import Path

from markupsafe import Markup
from sqlalchemy.orm import Session

from . import config

UPLOADS = Path(config.DATABASE_URL.replace("sqlite:///", "")).parent / "uploads" \
    if config.DATABASE_URL.startswith("sqlite:///") else config.ROOT_DIR / "data" / "uploads"

_TR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
               ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t",
                "u", "f", "h", "c", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"]))


def slugify(text: str, max_len: int = 70) -> str:
    s = "".join(_TR.get(ch, ch) for ch in text.lower())
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:max_len].strip("-") or "item"


def unique_slug(db: Session, model, title: str, current_id: int | None = None) -> str:
    base = slugify(title)
    slug, n = base, 2
    while True:
        q = db.query(model).filter(model.slug == slug)
        if current_id:
            q = q.filter(model.id != current_id)
        if not q.first():
            return slug
        slug, n = f"{base}-{n}", n + 1


def _inline(s: str) -> str:
    s = escape(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"<i>\1</i>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    return s


def render_text(text: str | None) -> Markup:
    """Простая разметка: пустая строка — новый абзац; «# », «## » — заголовки;
    «- » — список; «1. » — нумерованный список; «> » — стихи/речёвки; **жирный**, *курсив*, [ссылка](https://...)."""
    if not text:
        return Markup("")
    out = []
    for block in re.split(r"\n\s*\n", text.strip().replace("\r\n", "\n")):
        lines = [l for l in block.split("\n") if l.strip()]
        if not lines:
            continue
        first = lines[0].lstrip()
        if first.startswith("## "):
            out.append(f"<h3>{_inline(first[3:])}</h3>")
            lines = lines[1:]
        elif first.startswith("# "):
            out.append(f"<h2>{_inline(first[2:])}</h2>")
            lines = lines[1:]
        if not lines:
            continue
        if all(l.lstrip().startswith(("- ", "• ", "– ")) for l in lines):
            out.append("<ul>" + "".join(f"<li>{_inline(l.lstrip()[2:])}</li>" for l in lines) + "</ul>")
        elif all(re.match(r"^\s*\d+[.)]\s", l) for l in lines):
            out.append("<ol>" + "".join(f"<li>{_inline(re.sub(r'^\s*\d+[.)]\s', '', l))}</li>" for l in lines) + "</ol>")
        elif all(l.lstrip().startswith(">") for l in lines):
            out.append("<blockquote class='verse'>" + "<br>".join(_inline(l.lstrip()[1:].strip()) for l in lines) + "</blockquote>")
        else:
            out.append("<p>" + "<br>".join(_inline(l) for l in lines) + "</p>")
    return Markup("\n".join(out))


def plain_excerpt(text: str | None, n: int = 160) -> str:
    s = re.sub(r"[#>*\-]+", " ", text or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1].rsplit(" ", 1)[0] + "…"


ALLOWED_IMG = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_DOC = ALLOWED_IMG | {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".txt", ".odt", ".zip", ".mp3", ".mp4"}
MAX_UPLOAD = 50 * 1024 * 1024


async def save_upload(upload, folder: str, allowed: set[str]) -> tuple[str, str] | None:
    """Сохраняет файл из формы. Возвращает (имя_на_диске, исходное_имя) или None, если файла нет."""
    if upload is None or not getattr(upload, "filename", ""):
        return None
    ext = Path(upload.filename).suffix.lower()
    if ext not in allowed:
        raise ValueError(f"Файлы {ext or 'без расширения'} не поддерживаются")
    data = await upload.read()
    if len(data) > MAX_UPLOAD:
        raise ValueError("Файл больше 50 МБ")
    target_dir = UPLOADS / folder
    target_dir.mkdir(parents=True, exist_ok=True)
    name = f"{secrets.token_hex(8)}{ext}"
    (target_dir / name).write_bytes(data)
    return name, Path(upload.filename).name
