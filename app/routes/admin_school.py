"""Учебная часть: тесты, журнал посещаемости, карточка энерта (зачёты, баллы, выезд), оценочные листы."""
import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..db import (ACTIVITY_KINDS, EVAL_CRITERIA, GAME_SECTIONS, Activity, Attendance, EvalScore, Group, Lesson,
                  PlayroomCredit, Test, TestAttempt, User, new_token)
from ..permissions import effective_role, has_perm
from ..progress import compute
from ..web import check_csrf, get_db, render, require, require_any
from .admin import get_or_404

router = APIRouter(prefix="/admin")


def back(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def _date(raw) -> date | None:
    try:
        return date.fromisoformat(str(raw)) if raw else None
    except ValueError:
        raise HTTPException(400, "Неверная дата")


# ---------------------------------------------------------------- тесты

@router.get("/tests")
def tests(request: Request, user: User = Depends(require_any("tests.manage", "tests.grade")),
          db: Session = Depends(get_db)):
    items = db.query(Test).order_by(Test.id.desc()).all()
    stats = {}
    for t in items:
        att = t.attempts
        stats[t.id] = (len({a.user_id for a in att}), sum(1 for a in att if a.passed),
                       sum(1 for a in att if a.needs_review))
    return render(request, "admin/tests.html", user, tests=items, stats=stats)


@router.get("/tests/new")
def test_new(request: Request, user: User = Depends(require("tests.manage"))):
    return render(request, "admin/test_edit.html", user, t=None, questions_json="[]")


@router.get("/tests/{tid}")
def test_edit(tid: int, request: Request, user: User = Depends(require("tests.manage")), db: Session = Depends(get_db)):
    t = get_or_404(db, Test, tid)
    return render(request, "admin/test_edit.html", user, t=t, questions_json=json.dumps(t.questions or [], ensure_ascii=False))


def _clean_questions(raw: str) -> list:
    try:
        qs = json.loads(raw or "[]")
    except json.JSONDecodeError:
        raise HTTPException(400, "Не получилось прочитать вопросы")
    out = []
    for q in qs if isinstance(qs, list) else []:
        qtype = q.get("type") if q.get("type") in ("single", "multi", "text") else "single"
        text = str(q.get("text", "")).strip()[:2000]
        if not text:
            continue
        opts = [str(o).strip()[:500] for o in q.get("options", []) if str(o).strip()] if qtype != "text" else []
        corr = sorted({int(i) for i in q.get("correct", []) if str(i).isdigit() and int(i) < len(opts)})
        if qtype == "single":
            corr = corr[:1]
        out.append({"type": qtype, "text": text, "options": opts, "correct": corr,
                    "points": 0 if qtype == "text" else max(0.5, float(q.get("points", 1) or 1))})
    return out


@router.post("/tests/{tid}")
async def test_save(tid: int, request: Request, user: User = Depends(require("tests.manage")),
                    db: Session = Depends(get_db)):
    await check_csrf(request)
    form = await request.form()
    action = form.get("action", "save")
    t = get_or_404(db, Test, tid) if tid else Test(author_id=user.id)
    if action == "delete":
        db.delete(t)
        db.commit()
        return back("/admin/tests")
    if action == "new_link":
        t.token = new_token()
        db.commit()
        return back(f"/admin/tests/{t.id}")
    if action == "toggle":
        t.is_open = not t.is_open
        db.commit()
        return back(str(form.get("back") or "/admin/tests"))
    t.title = str(form.get("title", "")).strip()[:200] or "Тест"
    t.description = str(form.get("description", "")).strip()[:2000]
    t.pass_percent = max(1, min(100, int(form.get("pass_percent") or 60)))
    t.counts_for_progress = form.get("counts_for_progress") == "1"
    t.show_answers = form.get("show_answers") == "1"
    t.is_open = form.get("is_open") == "1"
    t.note = str(form.get("note", "")).strip()[:2000]
    t.questions = _clean_questions(str(form.get("questions_json", "[]")))
    if not tid:
        db.add(t)
    db.commit()
    return back(f"/admin/tests/{t.id}?saved=1")


@router.get("/tests/{tid}/results")
def test_results(tid: int, request: Request, user: User = Depends(require("tests.grade")), db: Session = Depends(get_db)):
    t = get_or_404(db, Test, tid)
    attempts = db.query(TestAttempt).filter(TestAttempt.test_id == tid).order_by(TestAttempt.id.desc()).all()
    return render(request, "admin/test_results.html", user, t=t, attempts=attempts)


@router.post("/attempts/{aid}")
async def attempt_review(aid: int, request: Request, user: User = Depends(require("tests.grade")),
                         db: Session = Depends(get_db)):
    await check_csrf(request)
    form = await request.form()
    a = get_or_404(db, TestAttempt, aid)
    a.passed = form.get("passed") == "1"
    a.needs_review = False
    a.reviewer_note = str(form.get("reviewer_note", "")).strip()[:1000]
    db.commit()
    return back(f"/admin/tests/{a.test_id}/results#a{a.id}")


# ---------------------------------------------------------------- журнал

@router.get("/journal")
def journal(request: Request, group: int = 0, user: User = Depends(require("journal.manage")),
            db: Session = Depends(get_db)):
    flows = db.query(Group).filter(Group.is_flow.is_(True)).order_by(Group.id.desc()).all()
    g = next((f for f in flows if f.id == group), flows[0] if flows else None)
    marks = {}
    rows = []
    if g:
        lesson_ids = [l.id for l in g.lessons]
        for m in db.query(Attendance).filter(Attendance.lesson_id.in_(lesson_ids)).all() if lesson_ids else []:
            marks[(m.lesson_id, m.user_id)] = m
        members = sorted([m for m in g.members if effective_role(m) == "energ"] or g.members,
                         key=lambda u: u.display_name)
        for u in members:
            p = compute(db, u)
            rows.append((u, p))
    return render(request, "admin/journal.html", user, flows=flows, g=g, marks=marks, rows=rows,
                  today=date.today().isoformat())


@router.post("/journal/{gid}")
async def journal_post(gid: int, request: Request, user: User = Depends(require("journal.manage")),
                       db: Session = Depends(get_db)):
    await check_csrf(request)
    form = await request.form()
    g = get_or_404(db, Group, gid)
    action = form.get("action")
    if action == "add_lesson":
        d = _date(form.get("date"))
        if not d:
            raise HTTPException(400, "Укажите дату занятия")
        db.add(Lesson(group_id=g.id, date=d, title=str(form.get("title", ""))[:200], is_exam=form.get("is_exam") == "1"))
    elif action == "delete_lesson":
        l = get_or_404(db, Lesson, int(form.get("lesson_id", 0)))
        if l.group_id == g.id:
            db.delete(l)
    elif action == "save_attendance":
        lid = int(form.get("lesson_id", 0))
        lesson = get_or_404(db, Lesson, lid)
        present = {int(x) for x in form.getlist("present")}
        excused = {int(x) for x in form.getlist("excused")}
        for u in g.members:
            m = db.get(Attendance, {"lesson_id": lid, "user_id": u.id})
            if m is None:
                m = Attendance(lesson_id=lid, user_id=u.id)
                db.add(m)
            m.present = u.id in present
            m.excused = u.id in excused and not m.present
        _ = lesson
    db.commit()
    return back(f"/admin/journal?group={g.id}")


@router.get("/journal/{gid}/lesson/{lid}")
def lesson_marks(gid: int, lid: int, request: Request, user: User = Depends(require("journal.manage")),
                 db: Session = Depends(get_db)):
    g = get_or_404(db, Group, gid)
    lesson = get_or_404(db, Lesson, lid)
    marks = {m.user_id: m for m in db.query(Attendance).filter(Attendance.lesson_id == lid)}
    return render(request, "admin/lesson.html", user, g=g, lesson=lesson, marks=marks,
                  members=sorted(g.members, key=lambda u: u.display_name))


# ---------------------------------------------------------------- карточка человека

@router.get("/people/{uid}")
def person(uid: int, request: Request, user: User = Depends(require_any("journal.manage", "eval.rate")),
           db: Session = Depends(get_db)):
    p = get_or_404(db, User, uid)
    evals = db.query(EvalScore).filter(EvalScore.user_id == uid).order_by(EvalScore.on_date.desc(), EvalScore.id.desc()).all()
    return render(request, "admin/person.html", user, p=p, progress=compute(db, p),
                  credits={c.section: c for c in db.query(PlayroomCredit).filter(PlayroomCredit.user_id == uid)},
                  activities=db.query(Activity).filter(Activity.user_id == uid).order_by(Activity.id.desc()).all(),
                  attempts=db.query(TestAttempt).filter(TestAttempt.user_id == uid).order_by(TestAttempt.id.desc()).all(),
                  evals=evals, today=date.today().isoformat(), ACTIVITY_KINDS=ACTIVITY_KINDS, sections=GAME_SECTIONS,
                  criteria=EVAL_CRITERIA)


@router.post("/people/{uid}")
async def person_post(uid: int, request: Request, user: User = Depends(require_any("journal.manage", "eval.rate")),
                      db: Session = Depends(get_db)):
    await check_csrf(request)
    form = await request.form()
    p = get_or_404(db, User, uid)
    action = form.get("action")
    journal_ok = has_perm(user, "journal.manage")
    if action == "credits" and journal_ok:
        wanted = {s for s in form.getlist("sections") if s in GAME_SECTIONS}
        existing = {c.section: c for c in db.query(PlayroomCredit).filter(PlayroomCredit.user_id == uid)}
        for s, c in existing.items():
            if s not in wanted:
                db.delete(c)
        for s in wanted - set(existing):
            db.add(PlayroomCredit(user_id=uid, section=s, by_id=user.id))
    elif action == "activity" and journal_ok:
        kind = form.get("kind")
        if kind not in ACTIVITY_KINDS:
            raise HTTPException(400)
        try:
            pts = float(str(form.get("points") or 0).replace(",", "."))
        except ValueError:
            raise HTTPException(400, "Баллы — число")
        if kind == "penalty":
            pts = -abs(pts)
        db.add(Activity(user_id=uid, kind=kind, points=pts, note=str(form.get("note", ""))[:300],
                        on_date=_date(form.get("on_date")) or date.today(), by_id=user.id))
    elif action == "delete_activity" and journal_ok:
        a = get_or_404(db, Activity, int(form.get("activity_id", 0)))
        if a.user_id == uid:
            db.delete(a)
    elif action == "eval" and has_perm(user, "eval.rate"):
        d = _date(form.get("on_date")) or date.today()
        for i, crit in enumerate(EVAL_CRITERIA):
            val = form.get(f"c{i}")
            if val and str(val).isdigit():
                db.add(EvalScore(user_id=uid, rater_id=user.id, criterion=crit, score=max(1, min(5, int(val))),
                                 comment=str(form.get(f"m{i}", ""))[:500], on_date=d))
    else:
        raise HTTPException(403, "Недостаточно прав")
    db.commit()
    return back(f"/admin/people/{p.id}")


# ---------------------------------------------------------------- оценочные листы (сводка)

@router.get("/eval")
def eval_summary(request: Request, user: User = Depends(require("eval.rate")), db: Session = Depends(get_db)):
    people = (db.query(User).filter(User.role.in_(["pedsostav", "curator", "org", "smm", "old", "master"]))
              .order_by(User.first_name).all())
    scores = db.query(EvalScore).all()
    table: dict[int, dict[str, list]] = {}
    for s in scores:
        table.setdefault(s.user_id, {}).setdefault(s.criterion, []).append(s.score)
    avg = {uid: {c: round(sum(v) / len(v), 1) for c, v in crit.items()} for uid, crit in table.items()}
    return render(request, "admin/eval.html", user, people=people, avg=avg, criteria=EVAL_CRITERIA)
