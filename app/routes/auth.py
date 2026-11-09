"""Вход через Telegram (виджет) и выход."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .. import config
from ..db import User, now
from ..telegram import verify_login, verify_webapp
from ..web import current_user, get_db, render

router = APIRouter()


def _safe_next(nxt: str | None) -> str:
    return nxt if nxt and nxt.startswith("/") and not nxt.startswith("//") else "/cabinet"


def _login(request: Request, db: Session, tg_id: int, **fields) -> User:
    user = db.query(User).filter(User.tg_id == tg_id).first()
    if user is None:
        user = User(tg_id=tg_id)
        db.add(user)
    for k, v in fields.items():
        if v is not None:
            setattr(user, k, v)
    user.last_login = now()
    db.commit()
    request.session.clear()
    request.session["uid"] = user.id
    request.session["super"] = tg_id in config.SUPERADMIN_IDS
    return user


@router.get("/login")
def login_page(request: Request, next: str | None = None, user: User | None = Depends(current_user)):
    if user:
        return RedirectResponse(_safe_next(next), status_code=303)
    request.session["next"] = _safe_next(next)
    return render(request, "login.html", None, next=_safe_next(next))


@router.get("/auth/telegram")
def auth_telegram(request: Request, db: Session = Depends(get_db)):
    data = {k: v for k, v in request.query_params.items()}
    if not verify_login(data):
        raise HTTPException(status_code=400, detail="Не получилось проверить вход через Telegram. Попробуйте ещё раз.")
    nxt = request.session.get("next")
    _login(
        request, db, int(data["id"]),
        username=data.get("username"),
        first_name=data.get("first_name"),
        last_name=data.get("last_name"),
        photo_url=data.get("photo_url"),
    )
    return RedirectResponse(_safe_next(nxt), status_code=303)


@router.get("/app")
def mini_app(request: Request, user: User | None = Depends(current_user)):
    """Точка входа Telegram Mini App: страница сама логинит по initData и ведёт в кабинет или базу."""
    return render(request, "miniapp.html", user)


@router.post("/auth/webapp")
async def auth_webapp(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    data = verify_webapp(str(form.get("init_data", "")))
    if not data or "id" not in data:
        raise HTTPException(status_code=400, detail="Не получилось войти через Telegram")
    _login(request, db, int(data["id"]), username=data.get("username"), first_name=data.get("first_name"),
           last_name=data.get("last_name"), photo_url=data.get("photo_url"))
    return {"ok": True}


@router.get("/auth/dev")
def auth_dev(request: Request, tg_id: int = 1, name: str = "Тестовый", db: Session = Depends(get_db)):
    """Вход без Телеграма для локальной разработки. На сервере DEV_LOGIN должен быть выключен."""
    if not config.DEV_LOGIN:
        raise HTTPException(status_code=404)
    _login(request, db, tg_id, first_name=name)
    return RedirectResponse("/cabinet", status_code=303)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=303)
