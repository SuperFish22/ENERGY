"""Точка входа сайта. Запуск: uvicorn app.main:app --reload"""
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager

from starlette.exceptions import HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import config
from .db import SessionLocal, init_db
from .routes import admin, admin_content, admin_school, auth, bot_api, cabinet, constructors, public, tests
from .web import current_user, render

@asynccontextmanager
async def lifespan(_app):
    init_db()
    from .seed import seed
    seed(verbose=False)
    yield


app = FastAPI(title=config.SITE_NAME, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SECRET_KEY,
    session_cookie="energy_session",
    max_age=60 * 60 * 24 * 30,
    same_site="lax",
    https_only=config.HTTPS_ONLY,
)
app.mount("/static", StaticFiles(directory=str(config.BASE_DIR / "static")), name="static")

for r in (public.router, auth.router, cabinet.router, tests.router, constructors.router,
          admin.router, admin_content.router, admin_school.router, bot_api.router):
    app.include_router(r)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    if exc.status_code in (301, 302, 303, 307) and exc.headers and "Location" in exc.headers:
        return RedirectResponse(exc.headers["Location"], status_code=exc.status_code)
    db = SessionLocal()
    try:
        user = current_user(request, db)
        titles = {404: "Такой страницы нет", 403: "Сюда нельзя", 400: "Что-то не так"}
        return render(request, "error.html", user, status_code=exc.status_code,
                      code=exc.status_code, title=titles.get(exc.status_code, "Ошибка"),
                      message=exc.detail if exc.status_code != 404 else "Возможно, её переместили или ещё не сделали.")
    finally:
        db.close()
