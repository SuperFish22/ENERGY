"""Роли, права и как они складываются.

Итоговые права человека = права его роли + права всех его активных (не истёкших) групп.
Руководитель может всё.
"""
from . import config
from .db import User

PERMISSIONS: dict[str, str] = {
    "leads.view": "Видеть заявки",
    "leads.manage": "Обрабатывать заявки",
    "users.manage": "Менять роли людей",
    "groups.manage": "Создавать и удалять группы, выдавать права",
    "journal.manage": "Вести журнал: посещаемость, зачёты игротеки, баллы, выезд",
    "eval.rate": "Заполнять оценочные листы (ENERGY PRO)",
    "playroom.edit": "Добавлять игры в игротеку",
    "kb.view_closed": "Видеть закрытую базу знаний",
    "kb.edit": "Добавлять материалы в базу",
    "kb.approve": "Одобрять игры, материалы и конструкторы в общую базу",
    "kb.rate": "Оценивать материалы и игры",
    "tests.manage": "Создавать тесты",
    "tests.grade": "Смотреть и проверять результаты тестов",
    "constructors.use": "Пользоваться конструкторами (игры, КТД, свечки, мероприятия)",
    "news.edit": "Вести слайдер и фото на главной",
}

_STAFF_BASE = {"kb.view_closed", "kb.rate", "constructors.use"}

ROLES: dict[str, dict] = {
    "leader": {"title": "Руководитель", "perms": set(PERMISSIONS)},
    "methodist": {"title": "Методист", "perms": _STAFF_BASE | {
        "kb.edit", "kb.approve", "playroom.edit", "tests.manage", "tests.grade", "eval.rate", "journal.manage"}},
    "master": {"title": "Мастер", "perms": _STAFF_BASE | {
        "leads.view", "kb.edit", "playroom.edit", "eval.rate", "tests.grade", "journal.manage"}},
    "curator": {"title": "Куратор", "perms": _STAFF_BASE | {"tests.grade", "journal.manage"}},
    "org": {"title": "Орг", "perms": _STAFF_BASE | {"kb.edit", "playroom.edit"}},
    "smm": {"title": "СМИ", "perms": _STAFF_BASE | {"news.edit"}},
    "old": {"title": "Старик", "perms": _STAFF_BASE | {"eval.rate"}},
    "pedsostav": {"title": "Педсостав (ENERGY PRO)", "perms": set(_STAFF_BASE)},
    "energ": {"title": "Энерт", "perms": set()},
}


def role_title(role: str) -> str:
    return ROLES.get(role, {}).get("title", role)


def effective_role(user: User) -> str:
    if user.tg_id in config.SUPERADMIN_IDS:
        return "leader"
    return user.role if user.role in ROLES else "energ"


def user_permissions(user: User | None) -> set[str]:
    if user is None or not user.is_active:
        return set()
    perms = set(ROLES[effective_role(user)]["perms"])
    for g in user.groups:
        if g.is_active:
            perms.update(p for p in (g.permissions or []) if p in PERMISSIONS)
    return perms


def has_perm(user: User | None, perm: str) -> bool:
    return perm in user_permissions(user)


ADMIN_PERMS = {"leads.view", "users.manage", "groups.manage", "journal.manage", "eval.rate", "playroom.edit",
               "kb.edit", "kb.approve", "tests.manage", "tests.grade", "news.edit"}


def is_staff(user: User | None) -> bool:
    """Показывать ли человеку ссылку в админку."""
    return bool(user_permissions(user) & ADMIN_PERMS)
