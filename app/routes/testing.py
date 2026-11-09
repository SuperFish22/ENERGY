"""Тестирование: тестовые пользователи под каждую роль и «Войти как…».

Доступно только главным админам (SUPERADMIN_IDS). Пока вы «вошли как» другой человек,
в сессии хранится ваш настоящий id (real_uid), и вернуться можно одной кнопкой.
Тестовые пользователи имеют отрицательный Telegram id — настоящий вход через Telegram с ними не пересечётся.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .. import config
from ..db import (Activity, Attendance, Construct, EvalScore, Group, PlayroomCredit, Rating, TestAttempt, User,
                  now)
from ..permissions import ROLES
from ..web import check_csrf, get_db

router = APIRouter()

TEST_ID_BASE = -100000  # тестовые tg_id: -100001, -100002, …
TEST_GROUP = "Тестовый поток"


def real_user(request: Request, db: Session) -> User | None:
    uid = request.session.get("real_uid") or request.session.get("uid")
    return db.get(User, uid) if uid else None


def require_superadmin(request: Request, db: Session = Depends(get_db)) -> User:
    u = real_user(request, db)
    if u is None or u.tg_id not in config.SUPERADMIN_IDS:
        raise HTTPException(403, "Это могут только главные админы (SUPERADMIN_IDS)")
    return u


def _test_users(db: Session):
    return db.query(User).filter(User.tg_id <= TEST_ID_BASE).order_by(User.tg_id.desc()).all()


# Сколько тестовых людей каждой роли предлагать по умолчанию
DEFAULT_COUNTS = {"energ": 10, "master": 2, "curator": 2}
MAX_PER_ROLE = 50
# Имена, чтобы в журнале и списках было проще различать тестовых энертов
TEST_NAMES = ["Аня", "Борис", "Вика", "Глеб", "Даша", "Егор", "Женя", "Зоя", "Илья", "Катя", "Лёва", "Маша",
              "Никита", "Оля", "Паша", "Рита", "Сеня", "Таня", "Ульяна", "Фёдор", "Хлоя", "Цезарь", "Чарли", "Шура",
              "Эля", "Юра", "Яна"]


@router.post("/admin/test-users")
async def create_test_users(request: Request, me: User = Depends(require_superadmin), db: Session = Depends(get_db)):
    """Создаёт тестовых людей: сколько указано в форме для каждой роли (поле n_<роль>).
    Без формы — по одному на роль и 10 энертов. Повторное нажатие добавляет ещё."""
    await check_csrf(request)
    form = await request.form()
    existing = _test_users(db)
    next_id = min([u.tg_id for u in existing] + [TEST_ID_BASE]) - 1
    per_role_count = {r: sum(1 for u in existing if u.role == r) for r in ROLES}
    for role, info in ROLES.items():
        raw = form.get(f"n_{role}")
        try:
            n = int(raw) if raw not in (None, "") else (DEFAULT_COUNTS.get(role, 1) if not existing else 0)
        except ValueError:
            n = 0
        for _ in range(max(0, min(n, MAX_PER_ROLE))):
            per_role_count[role] += 1
            k = per_role_count[role]
            if role == "energ":  # «Аня (тест-энерт 1)», «Борис (тест-энерт 2)»…
                first, last = TEST_NAMES[(k - 1) % len(TEST_NAMES)], f"(тест-энерт {k})"
            else:  # «Тест · Мастер», «Тест · Мастер 2»…
                first, last = "Тест", f"· {info['title']}" + (f" {k}" if k > 1 else "")
            db.add(User(tg_id=next_id, first_name=first, last_name=last, role=role,
                        username=f"test_{role}_{k}"))
            next_id -= 1
    db.flush()
    group = db.query(Group).filter(Group.name == TEST_GROUP).first()
    if group is None:
        group = Group(name=TEST_GROUP, description="Для проверки журнала, тестов и шкалы. Удаляется вместе с тестовыми пользователями.",
                      is_flow=True, created_by_id=me.id)
        db.add(group)
    for u in _test_users(db):
        if u.role in ("energ", "master", "curator") and u not in group.members:
            group.members.append(u)
    db.commit()
    return RedirectResponse("/admin/users?test=1", status_code=303)


@router.post("/admin/test-users/delete")
async def delete_test_users(request: Request, me: User = Depends(require_superadmin), db: Session = Depends(get_db)):
    await check_csrf(request)
    users = _test_users(db)
    ids = [u.id for u in users]
    if ids:
        for model in (Attendance, PlayroomCredit, Activity, EvalScore, TestAttempt, Rating):
            db.query(model).filter(model.user_id.in_(ids)).delete(synchronize_session=False)
        db.query(Construct).filter(Construct.author_id.in_(ids)).delete(synchronize_session=False)
        for u in users:
            u.groups.clear()
            db.delete(u)
    group = db.query(Group).filter(Group.name == TEST_GROUP).first()
    if group is not None:
        db.delete(group)
    db.commit()
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/admin/impersonate/{uid}")
async def impersonate(uid: int, request: Request, me: User = Depends(require_superadmin), db: Session = Depends(get_db)):
    await check_csrf(request)
    target = db.get(User, uid)
    if target is None:
        raise HTTPException(404)
    if target.id == me.id:
        return RedirectResponse("/admin", status_code=303)
    request.session["real_uid"] = me.id
    request.session["real_name"] = me.display_name
    request.session["uid"] = target.id
    return RedirectResponse("/cabinet", status_code=303)


@router.post("/impersonate/stop")
async def stop_impersonating(request: Request, db: Session = Depends(get_db)):
    await check_csrf(request)
    real_uid = request.session.pop("real_uid", None)
    request.session.pop("real_name", None)
    if real_uid:
        request.session["uid"] = real_uid
    return RedirectResponse("/admin/users", status_code=303)
