"""Конструкторы: игра, КТД, свечка/огонёк, мероприятие для СВ.

Черновик видит только автор. «Отправить в общую базу» → На одобрении → руководитель/методист одобряет →
видно всем, у кого есть доступ к конструкторам. Одобренную игру можно одним нажатием перенести в игротеку.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..constructors import CANDLE_BANK, CANDLE_RULES, SCHEMAS, parse_form
from ..db import CONSTRUCT_KINDS, Construct, Game, User
from ..permissions import has_perm
from ..utils import unique_slug
from ..web import check_csrf, get_db, ratings_for, render, require

router = APIRouter(prefix="/konstruktor")


def _get_visible(db: Session, cid: int, user: User) -> Construct:
    c = db.get(Construct, cid)
    if c is None:
        raise HTTPException(404)
    if c.author_id != user.id and c.status != "published" and not has_perm(user, "kb.approve"):
        raise HTTPException(404)
    return c


@router.get("")
def index(request: Request, kind: str = "", user: User = Depends(require("constructors.use")),
          db: Session = Depends(get_db)):
    mine = db.query(Construct).filter(Construct.author_id == user.id).order_by(Construct.updated_at.desc()).all()
    shared_q = db.query(Construct).filter(Construct.status == "published")
    if kind in CONSTRUCT_KINDS:
        shared_q = shared_q.filter(Construct.kind == kind)
    shared = shared_q.order_by(Construct.updated_at.desc()).all()
    return render(request, "konstruktor/index.html", user, mine=mine, shared=shared, kind=kind,
                  ratings=ratings_for(db, "construct", [c.id for c in shared]))


@router.get("/new/{kind}")
def new(kind: str, request: Request, user: User = Depends(require("constructors.use"))):
    if kind not in SCHEMAS:
        raise HTTPException(404)
    return render(request, "konstruktor/edit.html", user, c=None, kind=kind, schema=SCHEMAS[kind], data={},
                  bank=CANDLE_BANK, candle_rules=CANDLE_RULES)


@router.post("/new/{kind}")
async def create(kind: str, request: Request, user: User = Depends(require("constructors.use")),
                 db: Session = Depends(get_db)):
    await check_csrf(request)
    if kind not in SCHEMAS:
        raise HTTPException(404)
    form = await request.form()
    c = Construct(kind=kind, title=str(form.get("title", "")).strip()[:200] or "Без названия",
                  data=parse_form(kind, form), author_id=user.id,
                  status="pending" if form.get("action") == "submit" else "draft")
    db.add(c)
    db.commit()
    return RedirectResponse(f"/konstruktor/{c.id}", status_code=303)


@router.get("/{cid}")
def view(cid: int, request: Request, user: User = Depends(require("constructors.use")),
         db: Session = Depends(get_db)):
    from .public import _rating_ctx
    c = _get_visible(db, cid, user)
    return render(request, "konstruktor/view.html", user, c=c, schema=SCHEMAS[c.kind], data=c.data or {},
                  **_rating_ctx(db, user, "construct", c.id))


@router.get("/{cid}/edit")
def edit(cid: int, request: Request, user: User = Depends(require("constructors.use")), db: Session = Depends(get_db)):
    c = _get_visible(db, cid, user)
    if c.author_id != user.id and not has_perm(user, "kb.approve"):
        raise HTTPException(403, "Редактировать может только автор")
    return render(request, "konstruktor/edit.html", user, c=c, kind=c.kind, schema=SCHEMAS[c.kind], data=c.data or {},
                  bank=CANDLE_BANK, candle_rules=CANDLE_RULES)


@router.post("/{cid}")
async def update(cid: int, request: Request, user: User = Depends(require("constructors.use")),
                 db: Session = Depends(get_db)):
    await check_csrf(request)
    c = _get_visible(db, cid, user)
    form = await request.form()
    action = form.get("action", "save")
    approver = has_perm(user, "kb.approve")
    if action in ("save", "submit"):
        if c.author_id != user.id and not approver:
            raise HTTPException(403)
        c.title = str(form.get("title", "")).strip()[:200] or c.title
        c.data = parse_form(c.kind, form)
        if action == "submit" and c.status in ("draft", "rejected"):
            c.status = "pending"
        elif c.status == "published" and not approver:
            c.status = "pending"  # правка опубликованного — снова на одобрение
    elif action in ("approve", "reject") and approver:
        c.status = "published" if action == "approve" else "rejected"
        c.approved_by_id = user.id
    elif action == "to_playroom" and approver and c.kind == "game":
        d = c.data or {}
        parts = [d.get("goal", ""), d.get("rules", "")]
        if d.get("words"):
            parts.append("\n".join("> " + l for l in d["words"].splitlines() if l.strip()))
        if d.get("variations"):
            parts.append("## Варианты\n\n" + "\n".join("- " + v for v in d["variations"]))
        if d.get("safety"):
            parts.append("## Безопасность\n\n" + d["safety"])
        g = Game(slug=unique_slug(db, Game, c.title), title=c.title, section=d.get("section", "Другое"),
                 ages=d.get("ages", []), players=d.get("players", ""), duration=d.get("duration", ""),
                 place=d.get("place", ""), props=", ".join(d.get("props", [])),
                 body="\n\n".join(p for p in parts if p), status="published", is_public=True,
                 author_id=c.author_id, approved_by_id=user.id)
        db.add(g)
        db.commit()
        return RedirectResponse(f"/igroteka/{g.slug}", status_code=303)
    elif action == "delete" and (c.author_id == user.id or approver):
        db.delete(c)
        db.commit()
        return RedirectResponse("/konstruktor", status_code=303)
    db.commit()
    return RedirectResponse(f"/konstruktor/{c.id}", status_code=303)
