"""Личный кабинет."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from ..db import Construct, EvalScore, TestAttempt, User
from ..permissions import user_permissions
from ..progress import compute
from ..web import get_db, login_required, render

router = APIRouter()


@router.get("/cabinet")
def cabinet(request: Request, user: User = Depends(login_required), db: Session = Depends(get_db)):
    attempts = (db.query(TestAttempt).filter(TestAttempt.user_id == user.id)
                .order_by(TestAttempt.id.desc()).limit(10).all())
    evals = db.query(EvalScore).filter(EvalScore.user_id == user.id).all()
    eval_avg: dict[str, list] = {}
    for e in evals:
        eval_avg.setdefault(e.criterion, []).append(e.score)
    return render(
        request, "cabinet.html", user,
        progress=compute(db, user),
        groups=[g for g in user.groups if g.is_active],
        my_perms=sorted(user_permissions(user)),
        attempts=attempts,
        eval_avg={k: round(sum(v) / len(v), 1) for k, v in eval_avg.items()},
        my_constructs=db.query(Construct).filter(Construct.author_id == user.id)
                        .order_by(Construct.updated_at.desc()).limit(5).all(),
    )
