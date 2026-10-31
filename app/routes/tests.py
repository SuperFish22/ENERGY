"""Прохождение тестов по закрытой ссылке /t/<token>. Нужен вход через Telegram — результат идёт в кабинет."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..db import Test, TestAttempt, User
from ..web import check_csrf, current_user, get_db, render

router = APIRouter()


def grade(test: Test, form) -> tuple[list, float, float, bool]:
    """Проверяет ответы. Возвращает (answers, score, max_score, needs_review)."""
    answers, score, max_score, needs_review = [], 0.0, 0.0, False
    for i, q in enumerate(test.questions or []):
        key = f"q{i}"
        qtype = q.get("type", "single")
        if qtype == "text":
            val = str(form.get(key, "")).strip()[:3000]
            answers.append({"type": "text", "value": val})
            needs_review = needs_review or bool(val)
            continue
        pts = float(q.get("points", 1))
        max_score += pts
        chosen = sorted({int(v) for v in form.getlist(key) if str(v).isdigit()})
        correct = sorted(q.get("correct", []))
        ok = bool(correct) and chosen == correct
        if ok:
            score += pts
        answers.append({"type": qtype, "value": chosen, "ok": ok})
    return answers, score, max_score, needs_review


@router.get("/t/{token}")
def take_test(token: str, request: Request, user: User | None = Depends(current_user), db: Session = Depends(get_db)):
    test = db.query(Test).filter(Test.token == token).first()
    if test is None:
        raise HTTPException(404)
    if user is None:
        return RedirectResponse(f"/login?next=/t/{token}", status_code=303)
    attempts = (db.query(TestAttempt).filter(TestAttempt.test_id == test.id, TestAttempt.user_id == user.id)
                .order_by(TestAttempt.id.desc()).all())
    return render(request, "test_take.html", user, test=test, attempts=attempts)


@router.post("/t/{token}")
async def submit_test(token: str, request: Request, user: User | None = Depends(current_user),
                      db: Session = Depends(get_db)):
    await check_csrf(request)
    test = db.query(Test).filter(Test.token == token).first()
    if test is None:
        raise HTTPException(404)
    if user is None:
        return RedirectResponse(f"/login?next=/t/{token}", status_code=303)
    if not test.is_open:
        raise HTTPException(400, "Тест сейчас закрыт для ответов")
    form = await request.form()
    answers, score, max_score, needs_review = grade(test, form)
    passed = max_score > 0 and score / max_score * 100 >= test.pass_percent
    if max_score == 0:  # тест только из открытых вопросов
        passed, needs_review = False, True
    a = TestAttempt(test_id=test.id, user_id=user.id, answers=answers, score=score, max_score=max_score,
                    passed=passed, needs_review=needs_review)
    db.add(a)
    db.commit()
    return RedirectResponse(f"/t/{token}/result/{a.id}", status_code=303)


@router.get("/t/{token}/result/{aid}")
def test_result(token: str, aid: int, request: Request, user: User | None = Depends(current_user),
                db: Session = Depends(get_db)):
    a = db.get(TestAttempt, aid)
    if a is None or a.test.token != token or user is None or a.user_id != user.id:
        raise HTTPException(404)
    return render(request, "test_result.html", user, a=a, test=a.test)
