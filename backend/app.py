"""FastAPI 진입점. `uvicorn backend.app:app --reload`로 실행 (README.md 참고)."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from .auth_middleware import BasicAuthMiddleware
from .routers import category_list, companies, mailing, upload, validation

FRONTEND_INDEX = Path(__file__).resolve().parents[1] / "frontend" / "index.html"

app = FastAPI(title="기업분석 자동화 시스템")

app.add_middleware(BasicAuthMiddleware)

app.include_router(companies.router)
app.include_router(upload.router)
app.include_router(validation.router)
app.include_router(mailing.router)
app.include_router(category_list.router)


@app.get("/")
def index():
    # 화면을 고친 뒤 브라우저가 예전 index.html을 캐시에서 보여 주지 않도록 매번 새로 확인하게 한다.
    return FileResponse(FRONTEND_INDEX, headers={"Cache-Control": "no-cache"})
