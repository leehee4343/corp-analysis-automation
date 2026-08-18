"""FastAPI 진입점. `uvicorn backend.app:app --reload`로 실행 (README.md 참고)."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from .routers import category_list, companies, mailing, master_list, upload, validation

FRONTEND_INDEX = Path(__file__).resolve().parents[1] / "frontend" / "index.html"

app = FastAPI(title="기업분석 자동화 시스템")

app.include_router(companies.router)
app.include_router(upload.router)
app.include_router(validation.router)
app.include_router(mailing.router)
app.include_router(master_list.router)
app.include_router(category_list.router)


@app.get("/")
def index():
    return FileResponse(FRONTEND_INDEX)
