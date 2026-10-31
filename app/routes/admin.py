"""Админка: заявки, люди и роли, временные группы с правами."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from ..db import LEAD_STATUSES, Construct, Game, Group, Lead, Material, TestAttempt, User, now
from ..permissions import PERMISSIONS, ROLES, effective_role, has_perm, is_staff
from ..web import check_csrf, get_db, login_required, render, require

router = APIRouter(prefix="/admin")


def get_or_404(db: Session, model, obj_id: int):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(404)
    return obj


def back(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


@router.get("")
def dashboard(request: Request, user: User = Depends(login_required), db: Session = Depends(get_db)):
    if not is_staff(user):
        raise HTTPException(403, "Недостаточно прав")
    counts = dict(db.query(Lead.status, func.count(Lead.id)).group_by(Lead.status).all())
    return render(
        request, "admin/dashboard.html", user,
        counts=counts,
        users_total=db.query(func.count(User.id)).scalar(),
        groups_active=sum(1 for g in db.query(Group).all() if g.is_active),
        latest=db.query(Lead).order_by(Lead.id.desc()).limit(5).all() if has_perm(user, "leads.view") else [],
        pending=(db.query(Game).filter(Game.status == "pending").count()
                 + db.query(Material).filter(Material.status == "pending").count()
                 + db.query(Construct).filter(Construct.status == "pending").count()),
        to_review=db.query(TestAttempt).filter(TestAttempt.needs_review.is_(True)).count(),
        games_total=db.query(Game).filter(Game.status == "published").count(),
        materials_total=db.query(Material).filter(Material.status == "published").count(),
    )


# ---------- Заявки ----------

@router.get("/leads")
def leads(request: Request, status: str = "new", q: str = "",
          user: User = Depends(require("leads.view")), db: Session = Depends(get_db)):
    query = db.query(Lead)
    if status in LEAD_STATUSES:
        query = query.filter(Lead.status == status)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(Lead.full_name.ilike(like), Lead.phone.ilike(like), Lead.telegram.ilike(like)))
    counts = dict(db.query(Lead.status, func.count(Lead.id)).group_by(Lead.status).all())
    return render(request, "admin/leads.html", user, leads=query.order_by(Lead.id.desc()).limit(300).all(),
                  status=status, q=q, statuses=LEAD_STATUSES, counts=counts)


@router.post("/leads/{lead_id}")
async def lead_update(lead_id: int, request: Request,
                      user: User = Depends(require("leads.manage")), db: Session = Depends(get_db)):
    await check_csrf(request)
    form = await request.form()
    lead = get_or_404(db, Lead, lead_id)
    if form.get("status") in LEAD_STATUSES:
        lead.status = form["status"]
    if "admin_note" in form:
        lead.admin_note = str(form["admin_note"])[:2000]
    db.commit()
    return back(str(form.get("back") or "/admin/leads"))


# ---------- Люди ----------

@router.get("/users")
def users(request: Request, q: str = "", role: str = "",
          user: User = Depends(require("users.manage")), db: Session = Depends(get_db)):
    query = db.query(User)
    if role in ROLES:
        query = query.filter(User.role == role)
    if q:
        like = f"%{q.strip().lstrip('@')}%"
        query = query.filter(or_(User.first_name.ilike(like), User.last_name.ilike(like), User.username.ilike(like)))
    return render(request, "admin/users.html", user, people=query.order_by(User.id.desc()).limit(500).all(),
                  q=q, role=role)


@router.post("/users/{uid}")
async def user_update(uid: int, request: Request,
                      user: User = Depends(require("users.manage")), db: Session = Depends(get_db)):
    await check_csrf(request)
    form = await request.form()
    target = get_or_404(db, User, uid)
    new_role = form.get("role")
    if new_role in ROLES:
        # назначать руководителей может только руководитель
        if (new_role == "leader" or target.role == "leader") and effective_role(user) != "leader":
            raise HTTPException(403, "Назначать руководителей может только руководитель")
        target.role = new_role
    if "is_active" in form:
        if target.id == user.id:
            raise HTTPException(400, "Нельзя заблокировать самого себя")
        target.is_active = form["is_active"] == "1"
    db.commit()
    return back(str(form.get("back") or "/admin/users"))


# ---------- Группы ----------

def _parse_date(raw: str | None) -> datetime | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        raise HTTPException(400, "Неверная дата")


def _find_user(db: Session, ident: str) -> User | None:
    ident = ident.strip().lstrip("@")
    if not ident:
        return None
    if ident.isdigit():
        return db.query(User).filter(User.tg_id == int(ident)).first()
    return db.query(User).filter(func.lower(User.username) == ident.lower()).first()


@router.get("/groups")
def groups(request: Request, user: User = Depends(require("groups.manage")), db: Session = Depends(get_db)):
    all_groups = db.query(Group).order_by(Group.id.desc()).all()
    return render(request, "admin/groups.html", user, groups=all_groups, now=now())


@router.post("/groups")
async def group_create(request: Request, user: User = Depends(require("groups.manage")),
                       db: Session = Depends(get_db)):
    await check_csrf(request)
    form = await request.form()
    name = str(form.get("name", "")).strip()[:128]
    if not name:
        raise HTTPException(400, "Нужно название группы")
    g = Group(
        name=name,
        description=str(form.get("description", "")).strip()[:1000],
        permissions=[p for p in form.getlist("permissions") if p in PERMISSIONS],
        expires_at=_parse_date(form.get("expires_at")),
        is_flow=form.get("is_flow") == "1",
        created_by_id=user.id,
    )
    db.add(g)
    db.commit()
    return back(f"/admin/groups/{g.id}")


@router.get("/groups/{gid}")
def group_detail(gid: int, request: Request, user: User = Depends(require("groups.manage")),
                 db: Session = Depends(get_db)):
    g = get_or_404(db, Group, gid)
    return render(request, "admin/group_edit.html", user, g=g, error=request.query_params.get("error"))


@router.post("/groups/{gid}")
async def group_update(gid: int, request: Request, user: User = Depends(require("groups.manage")),
                       db: Session = Depends(get_db)):
    await check_csrf(request)
    form = await request.form()
    g = get_or_404(db, Group, gid)
    action = form.get("action")
    if action == "save":
        g.name = str(form.get("name", g.name)).strip()[:128] or g.name
        g.description = str(form.get("description", "")).strip()[:1000]
        g.permissions = [p for p in form.getlist("permissions") if p in PERMISSIONS]
        g.expires_at = _parse_date(form.get("expires_at"))
        g.is_flow = form.get("is_flow") == "1"
    elif action == "add_member":
        member = _find_user(db, str(form.get("member", "")))
        if member is None:
            return back(f"/admin/groups/{gid}?error=Человек не найден. Он должен хотя бы раз войти на сайт через Telegram.")
        if member not in g.members:
            g.members.append(member)
    elif action == "remove_member":
        member = db.get(User, int(form.get("user_id", 0)))
        if member in g.members:
            g.members.remove(member)
    elif action == "close":
        g.expires_at = now()
    elif action == "delete":
        db.delete(g)
        db.commit()
        return back("/admin/groups")
    db.commit()
    return back(f"/admin/groups/{gid}")
