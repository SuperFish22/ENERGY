"""Модели базы данных."""
import secrets
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    JSON, BigInteger, Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Table, Text,
    UniqueConstraint, create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from . import config

if config.DATABASE_URL.startswith("sqlite:///"):
    Path(config.DATABASE_URL.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    config.DATABASE_URL,
    connect_args={"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_token() -> str:
    return secrets.token_urlsafe(9)


# ---------------------------------------------------------------- люди и группы

group_members = Table(
    "group_members",
    Base.metadata,
    Column("group_id", ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    tg_id = Column(BigInteger, unique=True, index=True, nullable=False)
    username = Column(String(64))
    first_name = Column(String(128))
    last_name = Column(String(128))
    photo_url = Column(String(512))
    role = Column(String(32), default="energ", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=now)
    last_login = Column(DateTime, default=now)

    groups = relationship("Group", secondary=group_members, back_populates="members")

    @property
    def display_name(self) -> str:
        name = " ".join(x for x in [self.first_name, self.last_name] if x)
        return name or (f"@{self.username}" if self.username else f"id{self.tg_id}")


class Group(Base):
    """Временная группа: поток, команда (мастер + кураторы), орг-группа на выезд и т. п."""

    __tablename__ = "groups"

    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, default="")
    permissions = Column(JSON, default=list)
    is_flow = Column(Boolean, default=False)  # это поток: по нему ведётся журнал посещаемости
    expires_at = Column(DateTime, nullable=True)
    created_by_id = Column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=now)

    members = relationship("User", secondary=group_members, back_populates="groups")
    lessons = relationship("Lesson", back_populates="group", cascade="all, delete-orphan",
                           order_by="Lesson.date")

    @property
    def is_active(self) -> bool:
        return self.expires_at is None or self.expires_at > now()


# ---------------------------------------------------------------- заявки

class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True)
    full_name = Column(String(160), nullable=False)
    age = Column(Integer)
    phone = Column(String(32), nullable=False)
    telegram = Column(String(64))
    city = Column(String(160))
    source = Column(String(160))
    comment = Column(Text)
    course = Column(String(32), default="vozhatiy")
    status = Column(String(16), default="new", index=True)
    admin_note = Column(Text, default="")
    created_at = Column(DateTime, default=now, index=True)
    updated_at = Column(DateTime, default=now, onupdate=now)


LEAD_STATUSES = {"new": "Новая", "contacted": "Связались", "enrolled": "Зачислен", "rejected": "Отказ"}

# ---------------------------------------------------------------- контент: слайдер, игротека, база

# Статусы публикации для всего, что попадает «в общее» только после одобрения руководителей
PUB_STATUSES = {"draft": "Черновик", "pending": "На одобрении", "published": "Опубликовано", "rejected": "Отклонено"}


class Slide(Base):
    __tablename__ = "slides"

    id = Column(Integer, primary_key=True)
    image = Column(String(255), nullable=False)  # имя файла в data/uploads/slides
    title = Column(String(160), default="")
    caption = Column(String(300), default="")
    sort = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)


GAME_SECTIONS = [
    "Знакомство", "Тактильный барьер", "Выявление лидера", "Командообразование", "Сплочение",
    "Подвижные игры", "Игры-минутки", "Игры с залом", "Кричалки",
]
GAME_AGES = {"младший": "Младший (6–8)", "средний": "Средний (9–12)", "старший": "Старший (13–17)"}


class Game(Base):
    __tablename__ = "games"

    id = Column(Integer, primary_key=True)
    slug = Column(String(160), unique=True, index=True)
    title = Column(String(160), nullable=False)
    section = Column(String(64), index=True)
    ages = Column(JSON, default=list)  # ["младший", "средний"]
    players = Column(String(64), default="")  # «от 10», «весь отряд»
    duration = Column(String(64), default="")  # «10–15 мин»
    place = Column(String(32), default="")  # улица / помещение / любое
    props = Column(String(255), default="")  # реквизит
    body = Column(Text, default="")
    is_public = Column(Boolean, default=True)
    status = Column(String(16), default="draft", index=True)
    author_id = Column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_id = Column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    author = relationship("User", foreign_keys=[author_id])


KB_CATEGORIES = ["Теория", "Лекции", "Шаблоны", "Мероприятия и КТД", "Огоньки и свечки", "Методички", "Документы", "Для педсостава"]
KB_VISIBILITY = {"public": "Открытый (для всех, в поиске)", "closed": "Закрытый (по правам)", "link": "По закрытой ссылке"}


class Material(Base):
    """Материал базы знаний. Открытый — для всех и с инфографикой; закрытый — по правам; по ссылке — у кого ссылка."""

    __tablename__ = "materials"

    id = Column(Integer, primary_key=True)
    slug = Column(String(160), unique=True, index=True)
    title = Column(String(200), nullable=False)
    category = Column(String(64), index=True)
    summary = Column(String(400), default="")
    body = Column(Text, default="")
    key_points = Column(JSON, default=list)  # инфографика: [{"title": ..., "text": ...}]
    file_path = Column(String(255))  # имя файла в data/uploads/kb
    file_name = Column(String(255))
    visibility = Column(String(16), default="closed")
    link_token = Column(String(32), default=new_token, index=True)
    status = Column(String(16), default="draft", index=True)
    author_id = Column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_id = Column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    author = relationship("User", foreign_keys=[author_id])


class Rating(Base):
    """Оценка от вожатых: 1–5 звёзд + комментарий. kind = game | material | construct."""

    __tablename__ = "ratings"
    __table_args__ = (UniqueConstraint("user_id", "kind", "obj_id"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind = Column(String(16), nullable=False, index=True)
    obj_id = Column(Integer, nullable=False, index=True)
    stars = Column(Integer, nullable=False)
    comment = Column(Text, default="")
    created_at = Column(DateTime, default=now)

    user = relationship("User")


# ---------------------------------------------------------------- тесты

class Test(Base):
    """Тест. Раздаётся по закрытой ссылке /t/<token>. Вопросы — JSON:
    [{"type": "single|multi|text", "text": "...", "options": [...], "correct": [индексы], "points": 1}]
    """

    __tablename__ = "tests"

    id = Column(Integer, primary_key=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    token = Column(String(32), default=new_token, unique=True, index=True)
    questions = Column(JSON, default=list)
    pass_percent = Column(Integer, default=60)
    is_open = Column(Boolean, default=False)  # принимает ответы
    counts_for_progress = Column(Boolean, default=True)  # идёт в шкалу «Теория»
    show_answers = Column(Boolean, default=False)  # показать правильные ответы после сдачи
    note = Column(Text, default="")  # служебная заметка (например, «импортировано, проверить ответы»)
    author_id = Column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    attempts = relationship("TestAttempt", back_populates="test", cascade="all, delete-orphan")

    @property
    def max_score(self) -> float:
        return float(sum(q.get("points", 1) for q in self.questions or [] if q.get("type") != "text"))


class TestAttempt(Base):
    __tablename__ = "test_attempts"

    id = Column(Integer, primary_key=True)
    test_id = Column(ForeignKey("tests.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    answers = Column(JSON, default=list)
    score = Column(Float, default=0)
    max_score = Column(Float, default=0)
    passed = Column(Boolean, default=False)
    needs_review = Column(Boolean, default=False)  # есть открытые вопросы — проверяет мастер
    reviewer_note = Column(Text, default="")
    created_at = Column(DateTime, default=now)

    test = relationship("Test", back_populates="attempts")
    user = relationship("User")


# ---------------------------------------------------------------- журнал и шкала развития

class Lesson(Base):
    __tablename__ = "lessons"

    id = Column(Integer, primary_key=True)
    group_id = Column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(Date, nullable=False)
    title = Column(String(200), default="")
    is_exam = Column(Boolean, default=False)  # аттестационное занятие

    group = relationship("Group", back_populates="lessons")
    marks = relationship("Attendance", cascade="all, delete-orphan")


class Attendance(Base):
    __tablename__ = "attendance"

    lesson_id = Column(ForeignKey("lessons.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    present = Column(Boolean, default=True)
    excused = Column(Boolean, default=False)  # предупредил заранее


class PlayroomCredit(Base):
    """Зачёт по разделу игротеки (их 9)."""

    __tablename__ = "playroom_credits"
    __table_args__ = (UniqueConstraint("user_id", "section"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    section = Column(String(64), nullable=False)
    by_id = Column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=now)


ACTIVITY_KINDS = {
    "active": "Активность (+)",
    "penalty": "Штраф (−)",
    "trip": "Вожатский выезд",
    "exam": "Аттестация сдана",
    "practice": "Практика / мероприятие",
}


class Activity(Base):
    """Баллы рейтинга и отметки: активность, штрафы, выезд, аттестация, практика."""

    __tablename__ = "activities"

    id = Column(Integer, primary_key=True)
    user_id = Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    kind = Column(String(16), nullable=False)
    points = Column(Float, default=0)
    note = Column(String(300), default="")
    on_date = Column(Date)
    by_id = Column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=now)

    by = relationship("User", foreign_keys=[by_id])


EVAL_CRITERIA = [
    "Заморочка", "Активность", "Активность на лекциях (учёба)", "Игротека", "Трудные дети",
    "Я и напарник", "Внутренняя кухня", "Домашнее насилие и сложные темы", "Правила и безопасность",
]


class EvalScore(Base):
    """Оценочный лист (ENERGY PRO): оценка 1–5 по критерию за занятие."""

    __tablename__ = "eval_scores"

    id = Column(Integer, primary_key=True)
    user_id = Column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    rater_id = Column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    criterion = Column(String(80), nullable=False)
    score = Column(Integer, nullable=False)
    comment = Column(String(500), default="")
    on_date = Column(Date)
    created_at = Column(DateTime, default=now)

    rater = relationship("User", foreign_keys=[rater_id])


# ---------------------------------------------------------------- конструкторы

CONSTRUCT_KINDS = {
    "game": "Игра",
    "ktd": "КТД",
    "candle": "Свечка / огонёк",
    "event": "Мероприятие (для СВ)",
}


class Construct(Base):
    __tablename__ = "constructs"

    id = Column(Integer, primary_key=True)
    kind = Column(String(16), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    data = Column(JSON, default=dict)
    status = Column(String(16), default="draft", index=True)
    author_id = Column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by_id = Column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    author = relationship("User", foreign_keys=[author_id])


def init_db() -> None:
    Base.metadata.create_all(engine)
