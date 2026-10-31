"""Общие штуки для страниц: шаблоны, текущий пользователь, CSRF, проверка прав."""
import secrets
from datetime import datetime

from fastapi import Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from . import config
from .db import SessionLocal, User
from .db import CONSTRUCT_KINDS, GAME_AGES, GAME_SECTIONS, KB_VISIBILITY, PUB_STATUSES, Rating
from .permissions import PERMISSIONS, ROLES, effective_role, has_perm, is_staff, role_title, user_permissions
from .utils import plain_excerpt, render_text

templates = Jinja2Templates(directory=str(config.BASE_DIR / "templates"))
templates.env.globals.update(
    config=config,
    role_title=role_title,
    effective_role=effective_role,
    has_perm=has_perm,
    is_staff=is_staff,
    PERMISSIONS=PERMISSIONS,
    ROLES=ROLES,
    year=lambda: datetime.now().year,
    GAME_SECTIONS=GAME_SECTIONS,
    GAME_AGES=GAME_AGES,
    PUB_STATUSES=PUB_STATUSES,
    KB_VISIBILITY=KB_VISIBILITY,
    CONSTRUCT_KINDS=CONSTRUCT_KINDS,
)
templates.env.filters["md"] = render_text
templates.env.filters["excerpt"] = plain_excerpt


def fmt_dt(value: datetime | None, with_time: bool = True) -> str:
    if not value:
        return "—"
    return value.strftime("%d.%m.%Y %H:%M" if with_time else "%d.%m.%Y")


templates.env.filters["dt"] = fmt_dt


def ratings_for(db: Session, kind: str, ids) -> dict[int, tuple[float, int]]:
    """{id: (средняя оценка, сколько оценок)}"""
    from sqlalchemy import func
    ids = list(ids)
    if not ids:
        return {}
    rows = (db.query(Rating.obj_id, func.avg(Rating.stars), func.count(Rating.id))
            .filter(Rating.kind == kind, Rating.obj_id.in_(ids)).group_by(Rating.obj_id).all())
    return {r[0]: (round(float(r[1]), 1), r[2]) for r in rows}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    uid = request.session.get("uid")
    if not uid:
        return None
    user = db.get(User, uid)
    if user is None or not user.is_active:
        request.session.pop("uid", None)
        return None
    return user


def login_required(request: Request, user: User | None = Depends(current_user)) -> User:
    if user is None:
        raise HTTPException(status_code=303, headers={"Location": f"/login?next={request.url.path}"})
    return user


def require_any(*perms: str):
    def dep(user: User = Depends(login_required)) -> User:
        if not any(has_perm(user, p) for p in perms):
            raise HTTPException(status_code=403, detail="Недостаточно прав")
        return user
    return dep


def require(perm: str):
    def dep(user: User = Depends(login_required)) -> User:
        if not has_perm(user, perm):
            raise HTTPException(status_code=403, detail="Недостаточно прав")
        return user
    return dep


def csrf_token(request: Request) -> str:
    tok = request.session.get("csrf")
    if not tok:
        tok = secrets.token_urlsafe(24)
        request.session["csrf"] = tok
    return tok


async def check_csrf(request: Request) -> None:
    form = await request.form()
    sent = form.get("csrf") or request.headers.get("x-csrf-token")
    if not sent or not secrets.compare_digest(str(sent), request.session.get("csrf", "")):
        raise HTTPException(status_code=400, detail="Страница устарела, обновите её и попробуйте ещё раз")


def render(request: Request, name: str, user: User | None = None, status_code: int = 200, **ctx):
    ctx.update(user=user, csrf=csrf_token(request), perms=user_permissions(user))
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)
