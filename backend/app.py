"""FastAPI 진입점. `uvicorn backend.app:app --reload`로 실행 (README.md 참고)."""
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import auth_middleware as auth
from .auth_middleware import LoginMiddleware
from .routers import category_list, companies, export, mailing, pdfs, projects, sales, upload, validation

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
FRONTEND_INDEX = FRONTEND_DIR / "index.html"
FRONTEND_LOGIN = FRONTEND_DIR / "login.html"

app = FastAPI(title="기업분석 자동화 시스템")
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")  # 회사 심볼 등 화면 이미지

app.add_middleware(LoginMiddleware)

app.include_router(companies.router)
app.include_router(upload.router)
app.include_router(validation.router)
app.include_router(mailing.router)
app.include_router(category_list.router)
app.include_router(projects.router)
app.include_router(pdfs.router)
app.include_router(export.router)
app.include_router(sales.router)


@app.get("/")
def index():
    # 화면을 고친 뒤 브라우저가 예전 index.html을 캐시에서 보여 주지 않도록 매번 새로 확인하게 한다.
    return FileResponse(FRONTEND_INDEX, headers={"Cache-Control": "no-cache"})


# ----- 로그인 · 로그아웃 (auth_middleware 참고) -----
class LoginInput(BaseModel):
    username: str = ""
    password: str = ""


@app.get("/login")
def login_page(request: Request):
    # 로그인이 꺼져 있거나 이미 로그인했으면 바로 메인 화면으로
    if not auth.login_password() or auth.session_user(request.cookies.get(auth.COOKIE_NAME)):
        return RedirectResponse("/", status_code=303)
    return FileResponse(FRONTEND_LOGIN, headers={"Cache-Control": "no-cache"})


@app.post("/api/login")
def login(data: LoginInput, request: Request):
    if not auth.check_credentials(data.username.strip(), data.password):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다.")
    res = JSONResponse({"user": auth.login_user()})
    res.set_cookie(auth.COOKIE_NAME, auth.make_session_token(auth.login_user()), max_age=auth.SESSION_SECONDS,
                   httponly=True, samesite="lax", secure=auth.is_https(request), path="/")
    return res


@app.post("/api/logout")
def logout():
    res = JSONResponse({"ok": True})
    res.delete_cookie(auth.COOKIE_NAME, path="/")
    return res


@app.get("/api/session")
def session(request: Request):
    """화면이 로그아웃 링크를 보일지 정한다. auth_enabled=False면 로그인 없이 쓰는 환경."""
    enabled = bool(auth.login_password())
    return {"auth_enabled": enabled, "user": auth.session_user(request.cookies.get(auth.COOKIE_NAME)) if enabled else None}
