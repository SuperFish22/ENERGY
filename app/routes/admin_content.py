"""Админка контента: слайдер, игротека, база знаний, очередь одобрения."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..db import GAME_AGES, GAME_SECTIONS, KB_CATEGORIES, KB_VISIBILITY, Construct, Game, Material, Slide, User, new_token
from ..permissions import has_perm
from ..utils import ALLOWED_DOC, ALLOWED_IMG, UPLOADS, save_upload, unique_slug
from ..web import check_csrf, get_db, render, require
from .admin import get_or_404

router = APIRouter(prefix="/admin")


def back(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def _status_after_save(user: User, action: str, current: str) -> str:
    """Кто может — публикует сразу; остальные отправляют на одобрение руководителям."""
    if has_perm(user, "kb.approve"):
        return "published" if action == "publish" else ("draft" if action == "draft" else current or "published")
    if action == "submit":
        return "pending"
    if current == "published":
        return "pending"  # правка опубликованного — снова на одобрение
    return "draft" if current in ("", None, "rejected") else current


# ---------------------------------------------------------------- слайдер

@router.get("/slides")
def slides(request: Request, user: User = Depends(require("news.edit")), db: Session = Depends(get_db)):
    return render(request, "admin/slides.html", user, slides=db.query(Slide).order_by(Slide.sort, Slide.id).all(),
                  error=request.query_params.get("error"))


@router.post("/slides")
async def slides_post(request: Request, user: User = Depends(require("news.edit")), db: Session = Depends(get_db)):
    await check_csrf(request)
    form = await request.form()
    action = form.get("action")
    if action == "add":
        try:
            saved = await save_upload(form.get("image"), "slides", ALLOWED_IMG)
        except ValueError as e:
            return back(f"/admin/slides?error={e}")
        if not saved:
            return back("/admin/slides?error=Выберите фото")
        db.add(Slide(image=saved[0], title=str(form.get("title", ""))[:160], caption=str(form.get("caption", ""))[:300],
                     sort=int(form.get("sort") or 0)))
    else:
        s = get_or_404(db, Slide, int(form.get("id", 0)))
        if action == "save":
            s.title = str(form.get("title", ""))[:160]
            s.caption = str(form.get("caption", ""))[:300]
            s.sort = int(form.get("sort") or 0)
            s.is_active = form.get("is_active") == "1"
        elif action == "delete":
            (UPLOADS / "slides" / s.image).unlink(missing_ok=True)
            db.delete(s)
    db.commit()
    return back("/admin/slides")


# ---------------------------------------------------------------- игротека

@router.get("/games")
def games(request: Request, status: str = "", razdel: str = "", q: str = "",
          user: User = Depends(require("playroom.edit")), db: Session = Depends(get_db)):
    query = db.query(Game)
    if status:
        query = query.filter(Game.status == status)
    if razdel:
        query = query.filter(Game.section == razdel)
    if q:
        query = query.filter(Game.title.ilike(f"%{q}%"))
    return render(request, "admin/games.html", user, games=query.order_by(Game.section, Game.title).all(),
                  status=status, razdel=razdel, q=q)


@router.get("/games/new")
def game_new(request: Request, user: User = Depends(require("playroom.edit"))):
    return render(request, "admin/game_edit.html", user, g=None)


@router.get("/games/{gid}")
def game_edit(gid: int, request: Request, user: User = Depends(require("playroom.edit")), db: Session = Depends(get_db)):
    return render(request, "admin/game_edit.html", user, g=get_or_404(db, Game, gid))


@router.post("/games/{gid}")
async def game_save(gid: int, request: Request, user: User = Depends(require("playroom.edit")),
                    db: Session = Depends(get_db)):
    """gid = 0 — новая игра."""
    await check_csrf(request)
    form = await request.form()
    action = form.get("action", "save")
    g = get_or_404(db, Game, gid) if gid else Game(author_id=user.id, status="draft")
    if action == "delete":
        if not has_perm(user, "kb.approve"):
            raise HTTPException(403, "Удалять игры могут руководители и методисты")
        db.delete(g)
        db.commit()
        return back("/admin/games")
    title = str(form.get("title", "")).strip()[:160]
    if not title:
        raise HTTPException(400, "У игры должно быть название")
    if not g.slug or g.title != title:
        g.slug = unique_slug(db, Game, title, g.id)
    g.title = title
    g.section = form.get("section") if form.get("section") in GAME_SECTIONS else "Другое"
    g.ages = [a for a in form.getlist("ages") if a in GAME_AGES]
    for f in ("players", "duration", "place", "props"):
        setattr(g, f, str(form.get(f, "")).strip()[:255])
    g.body = str(form.get("body", ""))[:20000]
    g.is_public = form.get("is_public") == "1"
    g.status = _status_after_save(user, action, g.status)
    if g.status == "published":
        g.approved_by_id = user.id if has_perm(user, "kb.approve") else g.approved_by_id
    if not gid:
        db.add(g)
    db.commit()
    return back(f"/admin/games/{g.id}?saved=1")


# ---------------------------------------------------------------- база знаний

@router.get("/kb")
def kb(request: Request, status: str = "", cat: str = "", q: str = "",
       user: User = Depends(require("kb.edit")), db: Session = Depends(get_db)):
    query = db.query(Material)
    if status:
        query = query.filter(Material.status == status)
    if cat:
        query = query.filter(Material.category == cat)
    if q:
        query = query.filter(or_(Material.title.ilike(f"%{q}%"), Material.summary.ilike(f"%{q}%")))
    return render(request, "admin/kb.html", user, items=query.order_by(Material.updated_at.desc()).all(),
                  status=status, cat=cat, q=q, cats=KB_CATEGORIES)


@router.get("/kb/new")
def kb_new(request: Request, user: User = Depends(require("kb.edit"))):
    return render(request, "admin/kb_edit.html", user, m=None, cats=KB_CATEGORIES, error=None)


@router.get("/kb/{mid}")
def kb_edit(mid: int, request: Request, user: User = Depends(require("kb.edit")), db: Session = Depends(get_db)):
    return render(request, "admin/kb_edit.html", user, m=get_or_404(db, Material, mid), cats=KB_CATEGORIES,
                  error=request.query_params.get("error"))


@router.post("/kb/{mid}")
async def kb_save(mid: int, request: Request, user: User = Depends(require("kb.edit")), db: Session = Depends(get_db)):
    await check_csrf(request)
    form = await request.form()
    action = form.get("action", "save")
    m = get_or_404(db, Material, mid) if mid else Material(author_id=user.id, status="draft")
    if action == "delete":
        if not (has_perm(user, "kb.approve") or m.author_id == user.id):
            raise HTTPException(403)
        if m.file_path:
            (UPLOADS / "kb" / m.file_path).unlink(missing_ok=True)
        db.delete(m)
        db.commit()
        return back("/admin/kb")
    if action == "new_link":
        m.link_token = new_token()
        db.commit()
        return back(f"/admin/kb/{m.id}")
    title = str(form.get("title", "")).strip()[:200]
    if not title:
        raise HTTPException(400, "Нужно название")
    if not m.slug or m.title != title:
        m.slug = unique_slug(db, Material, title, m.id)
    m.title = title
    m.category = str(form.get("category", "")).strip()[:64] or "Теория"
    m.summary = str(form.get("summary", "")).strip()[:400]
    m.body = str(form.get("body", ""))[:100000]
    m.visibility = form.get("visibility") if form.get("visibility") in KB_VISIBILITY else "closed"
    titles, texts = form.getlist("kp_title"), form.getlist("kp_text")
    m.key_points = [{"title": t.strip()[:120], "text": x.strip()[:400]} for t, x in zip(titles, texts) if t.strip() or x.strip()]
    try:
        saved = await save_upload(form.get("file"), "kb", ALLOWED_DOC)
    except ValueError as e:
        return back(f"/admin/kb/{mid or ''}?error={e}" if mid else f"/admin/kb/new?error={e}")
    if saved:
        if m.file_path:
            (UPLOADS / "kb" / m.file_path).unlink(missing_ok=True)
        m.file_path, m.file_name = saved
    if form.get("remove_file") == "1" and m.file_path:
        (UPLOADS / "kb" / m.file_path).unlink(missing_ok=True)
        m.file_path = m.file_name = None
    m.status = _status_after_save(user, action, m.status)
    if m.status == "published" and has_perm(user, "kb.approve"):
        m.approved_by_id = user.id
    if not mid:
        db.add(m)
    db.commit()
    return back(f"/admin/kb/{m.id}?saved=1")


# ---------------------------------------------------------------- одобрение

@router.get("/approvals")
def approvals(request: Request, user: User = Depends(require("kb.approve")), db: Session = Depends(get_db)):
    return render(request, "admin/approvals.html", user,
                  games=db.query(Game).filter(Game.status == "pending").all(),
                  materials=db.query(Material).filter(Material.status == "pending").all(),
                  constructs=db.query(Construct).filter(Construct.status == "pending").all())


@router.post("/approvals")
async def approvals_post(request: Request, user: User = Depends(require("kb.approve")), db: Session = Depends(get_db)):
    await check_csrf(request)
    form = await request.form()
    model = {"game": Game, "material": Material, "construct": Construct}.get(str(form.get("kind")))
    if model is None:
        raise HTTPException(400)
    obj = get_or_404(db, model, int(form.get("id", 0)))
    obj.status = "published" if form.get("action") == "approve" else "rejected"
    obj.approved_by_id = user.id
    db.commit()
    return back("/admin/approvals")
