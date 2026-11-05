"""Публичные страницы: главная, визитка, игротека, открытая база знаний, заявка, robots.txt, sitemap.xml."""
import re
import time
from collections import defaultdict, deque

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from .. import config
from ..db import GAME_AGES, GAME_SECTIONS, Game, Lead, Material, Rating, Slide, User
from ..permissions import has_perm
from ..telegram import notify_new_lead
from ..utils import UPLOADS
from ..web import check_csrf, current_user, get_db, login_required, ratings_for, render

router = APIRouter()

_hits: dict[str, deque] = defaultdict(deque)


def _rate_limited(ip: str, limit: int = 5, window: int = 600) -> bool:
    q, t = _hits[ip], time.time()
    while q and t - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        return True
    q.append(t)
    return False


def _landing_ctx(db: Session) -> dict:
    return {
        "slides": db.query(Slide).filter(Slide.is_active.is_(True)).order_by(Slide.sort, Slide.id).all(),
        "games_count": db.query(func.count(Game.id)).filter(Game.status == "published", Game.is_public.is_(True)).scalar(),
        "fresh_games": db.query(Game).filter(Game.status == "published", Game.is_public.is_(True))
                         .order_by(func.random()).limit(6).all(),
    }


@router.get("/")
def index(request: Request, user: User | None = Depends(current_user), db: Session = Depends(get_db)):
    return render(request, "index.html", user, **_landing_ctx(db))


@router.get("/vizitka")
def vizitka(request: Request, user: User | None = Depends(current_user), db: Session = Depends(get_db)):
    """Режим визитки для ПК: полноэкранные слайды, листаются колесом и стрелками."""
    return render(request, "vizitka.html", user, **_landing_ctx(db))


@router.get("/privacy")
def privacy(request: Request, user: User | None = Depends(current_user)):
    return render(request, "privacy.html", user)


# ---------------------------------------------------------------- игротека

def _visible_games(db: Session, user: User | None):
    q = db.query(Game).filter(Game.status == "published")
    if not has_perm(user, "kb.view_closed"):
        q = q.filter(Game.is_public.is_(True))
    return q


@router.get("/igroteka")
def igroteka(request: Request, razdel: str = "", vozrast: str = "", q: str = "",
             user: User | None = Depends(current_user), db: Session = Depends(get_db)):
    query = _visible_games(db, user)
    if razdel in GAME_SECTIONS:
        query = query.filter(Game.section == razdel)
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(or_(Game.title.ilike(like), Game.body.ilike(like)))
    games = query.order_by(Game.section, Game.title).all()
    if vozrast in GAME_AGES:
        games = [g for g in games if vozrast in (g.ages or [])]
    counts = dict(_visible_games(db, user).with_entities(Game.section, func.count(Game.id)).group_by(Game.section).all())
    return render(request, "igroteka.html", user, games=games, razdel=razdel, vozrast=vozrast, q=q,
                  counts=counts, ratings=ratings_for(db, "game", [g.id for g in games]))


@router.get("/igroteka/{slug}")
def game_page(slug: str, request: Request, user: User | None = Depends(current_user), db: Session = Depends(get_db)):
    g = db.query(Game).filter(Game.slug == slug).first()
    if g is None or (g.status != "published" and not has_perm(user, "kb.approve")
                     and not (user and g.author_id == user.id)):
        raise HTTPException(404)
    if not g.is_public and not has_perm(user, "kb.view_closed"):
        raise HTTPException(404)
    same = (_visible_games(db, user).filter(Game.section == g.section, Game.id != g.id)
            .order_by(func.random()).limit(4).all())
    return render(request, "game.html", user, g=g, same=same, **_rating_ctx(db, user, "game", g.id))


# ---------------------------------------------------------------- база знаний

def _rating_ctx(db: Session, user: User | None, kind: str, obj_id: int) -> dict:
    rows = db.query(Rating).filter(Rating.kind == kind, Rating.obj_id == obj_id).order_by(Rating.id.desc()).all()
    mine = next((r for r in rows if user and r.user_id == user.id), None)
    avg = round(sum(r.stars for r in rows) / len(rows), 1) if rows else None
    return {"rating_rows": rows, "rating_avg": avg, "rating_mine": mine, "rating_kind": kind, "rating_obj": obj_id}


def _visible_materials(db: Session, user: User | None):
    q = db.query(Material).filter(Material.status == "published")
    if not has_perm(user, "kb.view_closed"):
        q = q.filter(Material.visibility == "public")
    else:
        q = q.filter(Material.visibility.in_(["public", "closed"]))
    return q


@router.get("/baza")
def baza(request: Request, cat: str = "", q: str = "", user: User | None = Depends(current_user),
         db: Session = Depends(get_db)):
    query = _visible_materials(db, user)
    if cat:
        query = query.filter(Material.category == cat)
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(or_(Material.title.ilike(like), Material.summary.ilike(like), Material.body.ilike(like)))
    items = query.order_by(Material.category, Material.title).all()
    cats = [c for (c,) in _visible_materials(db, user).with_entities(Material.category).distinct().all() if c]
    return render(request, "baza.html", user, items=items, cat=cat, q=q, cats=sorted(cats),
                  ratings=ratings_for(db, "material", [m.id for m in items]))


def _material_allowed(m: Material, user: User | None, via_link: bool = False) -> bool:
    if m.status != "published":
        return has_perm(user, "kb.approve") or (user is not None and m.author_id == user.id)
    if m.visibility == "public":
        return True
    if m.visibility == "link":
        return via_link or has_perm(user, "kb.edit")
    return has_perm(user, "kb.view_closed")


@router.get("/baza/{slug}")
def material_page(slug: str, request: Request, user: User | None = Depends(current_user), db: Session = Depends(get_db)):
    m = db.query(Material).filter(Material.slug == slug).first()
    if m is None or not _material_allowed(m, user):
        if m is not None and m.visibility == "closed" and user is None:
            return RedirectResponse(f"/login?next=/baza/{slug}", status_code=303)
        raise HTTPException(404)
    return render(request, "material.html", user, m=m, via_link=False, **_rating_ctx(db, user, "material", m.id))


@router.get("/m/{token}")
def material_by_link(token: str, request: Request, user: User | None = Depends(current_user),
                     db: Session = Depends(get_db)):
    m = db.query(Material).filter(Material.link_token == token, Material.status == "published").first()
    if m is None:
        raise HTTPException(404)
    request.session.setdefault("links", [])
    if token not in request.session["links"]:
        request.session["links"] = (request.session["links"] + [token])[-50:]
    return render(request, "material.html", user, m=m, via_link=True, **_rating_ctx(db, user, "material", m.id))


@router.get("/files/kb/{mid}")
def material_file(mid: int, request: Request, user: User | None = Depends(current_user), db: Session = Depends(get_db)):
    m = db.get(Material, mid)
    if m is None or not m.file_path:
        raise HTTPException(404)
    via_link = m.link_token in request.session.get("links", [])
    if not _material_allowed(m, user, via_link=via_link):
        raise HTTPException(403, "Этот файл доступен только команде ENERGY")
    path = UPLOADS / "kb" / m.file_path
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, filename=m.file_name or m.file_path)


@router.get("/media/slides/{name}")
def slide_image(name: str):
    if "/" in name or ".." in name:
        raise HTTPException(404)
    path = UPLOADS / "slides" / name
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, headers={"Cache-Control": "public, max-age=604800"})


# ---------------------------------------------------------------- оценки от вожатых

@router.post("/rate/{kind}/{obj_id}")
async def rate(kind: str, obj_id: int, request: Request, user: User = Depends(login_required),
               db: Session = Depends(get_db)):
    await check_csrf(request)
    if kind not in ("game", "material", "construct") or not has_perm(user, "kb.rate"):
        raise HTTPException(403, "Оценивать могут вожатые и педсостав ENERGY")
    form = await request.form()
    try:
        stars = max(1, min(5, int(form.get("stars", 0))))
    except ValueError:
        raise HTTPException(400, "Поставьте от 1 до 5 звёзд")
    r = db.query(Rating).filter(Rating.user_id == user.id, Rating.kind == kind, Rating.obj_id == obj_id).first()
    if r is None:
        r = Rating(user_id=user.id, kind=kind, obj_id=obj_id, stars=stars)
        db.add(r)
    r.stars = stars
    r.comment = str(form.get("comment", "")).strip()[:1000]
    db.commit()
    return RedirectResponse(str(form.get("back") or "/") + "#otzyvy", status_code=303)


# ---------------------------------------------------------------- заявка

PHONE_RE = re.compile(r"^\+?[\d\s\-()]{10,20}$")


@router.post("/api/lead")
async def create_lead(request: Request, bg: BackgroundTasks, db: Session = Depends(get_db)):
    wants_json = "application/json" in request.headers.get("accept", "")
    form = await request.form()

    def fail(msg: str, code: int = 400):
        if wants_json:
            return JSONResponse({"ok": False, "error": msg}, status_code=code)
        return RedirectResponse(f"/?lead_error={msg}#zayavka", status_code=303)

    await check_csrf(request)
    if form.get("website"):  # ловушка для ботов
        return JSONResponse({"ok": True}) if wants_json else RedirectResponse("/?sent=1#zayavka", 303)

    full_name = str(form.get("full_name", "")).strip()[:160]
    phone = str(form.get("phone", "")).strip()[:32]
    if len(full_name) < 2:
        return fail("Напишите, как вас зовут")
    if not PHONE_RE.match(phone) or len(re.sub(r"\D", "", phone)) < 10:
        return fail("Проверьте номер телефона")
    if not form.get("consent"):
        return fail("Нужно согласие на обработку персональных данных")
    age_raw = str(form.get("age", "")).strip()
    age = int(age_raw) if age_raw.isdigit() and 12 <= int(age_raw) <= 99 else None

    # nginx кладёт настоящий адрес посетителя в X-Real-IP (X-Forwarded-For можно подделать)
    ip = request.headers.get("x-real-ip") or (request.client.host if request.client else "?")
    if _rate_limited(ip):
        return fail("Слишком много заявок подряд. Попробуйте позже.", 429)

    lead = Lead(
        full_name=full_name, phone=phone, age=age,
        telegram=str(form.get("telegram", "")).strip()[:64] or None,
        city=str(form.get("city", "")).strip()[:160] or None,
        source=str(form.get("source", "")).strip()[:160] or None,
        comment=str(form.get("comment", "")).strip()[:2000] or None,
    )
    db.add(lead)
    db.commit()
    bg.add_task(notify_new_lead, lead)
    if wants_json:
        return JSONResponse({"ok": True})
    return RedirectResponse("/?sent=1#zayavka", status_code=303)


# ---------------------------------------------------------------- robots / sitemap

@router.get("/robots.txt", response_class=PlainTextResponse)
def robots():
    closed = ["/admin", "/cabinet", "/konstruktor", "/login", "/logout", "/auth/", "/api/", "/t/", "/m/",
              "/files/", "/rate/"]
    rules = "".join(f"Disallow: {p}\n" for p in closed)
    return (
        "User-agent: *\n" + rules + "Disallow: /*?lead_error=\nDisallow: /*?sent=\n\n"
        "User-agent: Yandex\n" + rules +
        "Clean-param: sent&lead_error&utm_source&utm_medium&utm_campaign&utm_content&utm_term /\n\n"
        f"Sitemap: {config.SITE_URL}/sitemap.xml\n"
    )


@router.get("/sitemap.xml")
def sitemap(db: Session = Depends(get_db)):
    pages = [("/", "weekly", "1.0", None), ("/igroteka", "weekly", "0.9", None), ("/baza", "weekly", "0.8", None),
             ("/privacy", "yearly", "0.2", None)]
    pages += [(f"/igroteka/{s}", "monthly", "0.7", u) for s, u in
              db.query(Game.slug, Game.updated_at).filter(Game.status == "published", Game.is_public.is_(True))]
    pages += [(f"/baza/{s}", "monthly", "0.7", u) for s, u in
              db.query(Material.slug, Material.updated_at).filter(Material.status == "published",
                                                                   Material.visibility == "public")]
    items = "".join(
        f"  <url><loc>{config.SITE_URL}{path}</loc>"
        + (f"<lastmod>{upd.date().isoformat()}</lastmod>" if upd else "")
        + f"<changefreq>{freq}</changefreq><priority>{prio}</priority></url>\n"
        for path, freq, prio, upd in pages
    )
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + items + "</urlset>\n")
    return Response(xml, media_type="application/xml")
