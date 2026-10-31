"""Шкала развития энерта — считается из реальных данных.

Блоки и веса можно менять здесь. Сумма весов = 100.
Логика повторяет устройство потока ENERGY (из вводной лекции):
  • после каждого занятия — тест (зачёт / незачёт);
  • игротека — 9 разделов, зачёт по каждому;
  • посещаемость — допустимо не больше 3 пропусков за поток;
  • рейтинг «Активность / Штрафы»;
  • обязательный вожатский выезд после потока;
  • аттестация на последнем занятии.
"""
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from .db import GAME_SECTIONS, Activity, Attendance, Lesson, PlayroomCredit, Test, TestAttempt, User

MAX_ABSENCES = 3  # допустимо пропусков за поток
ACTIVITY_TARGET = 20  # столько чистых баллов активности = полный блок

WEIGHTS = {
    "theory": 25,
    "playroom": 25,
    "attendance": 20,
    "activity": 10,
    "trip": 10,
    "exam": 10,
}

LEVELS = [(0, "Искра"), (25, "Заряд"), (60, "Энергия"), (90, "Молния")]


@dataclass
class Block:
    key: str
    title: str
    weight: int
    hint: str
    done: float = 0.0  # 0..1
    detail: str = ""
    items: list = field(default_factory=list)

    @property
    def points(self) -> float:
        return round(self.weight * max(0.0, min(1.0, self.done)), 1)


def compute(db: Session, user: User) -> dict:
    blocks: list[Block] = []

    # --- Теория: зачтённые тесты из тех, что идут в шкалу
    tests = db.query(Test).filter(Test.counts_for_progress.is_(True)).all()
    passed_ids = {a.test_id for a in db.query(TestAttempt).filter(
        TestAttempt.user_id == user.id, TestAttempt.passed.is_(True)).all()}
    t_total = len(tests)
    t_done = sum(1 for t in tests if t.id in passed_ids)
    blocks.append(Block("theory", "Теория", WEIGHTS["theory"],
                        "Тест после каждого занятия, формат зачёт / незачёт",
                        t_done / t_total if t_total else 0, f"{t_done} из {t_total} тестов",
                        [(t.title, t.id in passed_ids) for t in tests]))

    # --- Игротека: 9 разделов
    credited = {c.section for c in db.query(PlayroomCredit).filter(PlayroomCredit.user_id == user.id)}
    blocks.append(Block("playroom", "Игротека", WEIGHTS["playroom"],
                        "Зачёт по каждому из 9 разделов игр (тетрадь с играми = допуск к экзамену)",
                        len(credited) / len(GAME_SECTIONS), f"{len(credited)} из {len(GAME_SECTIONS)} разделов",
                        [(s, s in credited) for s in GAME_SECTIONS]))

    # --- Посещаемость: занятия потоков, где состоит человек
    flow_ids = [g.id for g in user.groups if g.is_flow]
    lessons = db.query(Lesson).filter(Lesson.group_id.in_(flow_ids)).all() if flow_ids else []
    marks = {m.lesson_id: m for m in db.query(Attendance).filter(Attendance.user_id == user.id)}
    held = [l for l in lessons if l.id in marks]  # занятие считается, когда по нему есть отметка
    present = sum(1 for l in held if marks[l.id].present)
    absent = len(held) - present
    blocks.append(Block("attendance", "Посещаемость", WEIGHTS["attendance"],
                        f"Отмечает мастер или куратор. Допустимо не больше {MAX_ABSENCES} пропусков",
                        present / len(held) if held else 0,
                        f"{present} из {len(held)} занятий" + (f" · пропусков: {absent}" if absent else "")))

    # --- Активность / штрафы
    acts = db.query(Activity).filter(Activity.user_id == user.id).all()
    plus = sum(a.points for a in acts if a.kind in ("active", "practice"))
    minus = sum(abs(a.points) for a in acts if a.kind == "penalty")
    net = plus - minus
    blocks.append(Block("activity", "Активность", WEIGHTS["activity"],
                        "Баллы рейтинга: активность на занятиях и вне их, вечерки, практика. Штрафы вычитаются",
                        net / ACTIVITY_TARGET, f"{net:g} баллов (+{plus:g} / −{minus:g})"))

    # --- Выезд и аттестация
    trip = any(a.kind == "trip" for a in acts)
    exam = any(a.kind == "exam" for a in acts)
    blocks.append(Block("trip", "Вожатский выезд", WEIGHTS["trip"],
                        "Обязательный выезд после потока", 1 if trip else 0, "есть" if trip else "ещё впереди"))
    blocks.append(Block("exam", "Аттестация", WEIGHTS["exam"],
                        "Зачёт по играм и устный блок по теории на последнем занятии",
                        1 if exam else 0, "сдана" if exam else "ещё впереди"))

    total = round(sum(b.points for b in blocks))
    level, next_level = LEVELS[0][1], None
    for i, (threshold, name) in enumerate(LEVELS):
        if total >= threshold:
            level = name
            next_level = LEVELS[i + 1] if i + 1 < len(LEVELS) else None
    warnings = []
    if absent > MAX_ABSENCES:
        warnings.append(f"Пропусков больше допустимого ({absent} из {MAX_ABSENCES}) — поговори с мастером.")
    elif absent == MAX_ABSENCES:
        warnings.append("Использованы все допустимые пропуски.")
    return {"total": total, "blocks": blocks, "level": level, "next_level": next_level, "levels": LEVELS,
            "warnings": warnings, "absent": absent}
