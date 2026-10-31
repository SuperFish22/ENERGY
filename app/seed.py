"""Начальное наполнение базы: игротека (133 игры из методичек ENERGY), тесты (из Google Форм),
две открытые статьи и фото для слайдера. Запускается само при первом старте, если таблицы пустые.

Вручную:  python -m app.seed
"""
import json
import shutil
from pathlib import Path

from .db import Game, Material, SessionLocal, Slide, Test, init_db
from .utils import UPLOADS, unique_slug

DATA = Path(__file__).parent / "seed_data"


def seed(verbose: bool = True) -> None:
    init_db()
    db = SessionLocal()
    log = print if verbose else (lambda *a: None)
    try:
        if not db.query(Game).first():
            for g in json.loads((DATA / "games.json").read_text(encoding="utf-8")):
                db.add(Game(slug=unique_slug(db, Game, g["title"]), title=g["title"], section=g["section"],
                            ages=g.get("age") or [], body=g["body"], is_public=True, status="published"))
                db.flush()
            log("Игротека: загружены игры из методичек")
        if not db.query(Test).first():
            for t in json.loads((DATA / "tests.json").read_text(encoding="utf-8")):
                db.add(Test(
                    title=t["title"], questions=t["questions"], is_open=False, counts_for_progress=True,
                    description="Тест по теме занятия. Формат — зачёт / незачёт.",
                    note=("Импортировано из Google Форм. Правильные ответы восстановлены по ответам лучших "
                          "участников — проверьте их перед тем, как открыть тест. Открытые вопросы проверяет мастер."),
                ))
            log("Тесты: импортированы 5 тестов (закрыты, ждут проверки)")
        if not db.query(Material).first():
            for m in json.loads((DATA / "materials.json").read_text(encoding="utf-8")):
                db.add(Material(slug=unique_slug(db, Material, m["title"]), title=m["title"], category=m["category"],
                                summary=m["summary"], body=m["body"], key_points=m["key_points"],
                                visibility=m["visibility"], status="pending"))
                db.flush()
            log("База знаний: 2 открытые статьи (на одобрении)")
        if not db.query(Slide).first():
            src = Path(__file__).parent / "static" / "img" / "seed" / "team.jpg"
            if src.exists():
                (UPLOADS / "slides").mkdir(parents=True, exist_ok=True)
                shutil.copy(src, UPLOADS / "slides" / "team.jpg")
                db.add(Slide(image="team.jpg", title="Мы — ENERGY", caption="Поток школы вожатых", sort=0))
                log("Слайдер: добавлено фото команды")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    seed()
