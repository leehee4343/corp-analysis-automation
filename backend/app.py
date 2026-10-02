"""FastAPI 진입점. `uvicorn backend.app:app --reload`로 실행 (README.md 참고)."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .auth_middleware import BasicAuthMiddleware
from .routers import category_list, companies, export, mailing, pdfs, projects, upload, validation

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"
FRONTEND_INDEX = FRONTEND_DIR / "index.html"

app = FastAPI(title="기업분석 자동화 시스템")
app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")  # 회사 심볼 등 화면 이미지

app.add_middleware(BasicAuthMiddleware)

app.include_router(companies.router)
app.include_router(upload.router)
app.include_router(validation.router)
app.include_router(mailing.router)
app.include_router(category_list.router)
app.include_router(projects.router)
app.include_router(pdfs.router)
app.include_router(export.router)


@app.get("/")
def index():
    # 화면을 고친 뒤 브라우저가 예전 index.html을 캐시에서 보여 주지 않도록 매번 새로 확인하게 한다.
    return FileResponse(FRONTEND_INDEX, headers={"Cache-Control": "no-cache"})
