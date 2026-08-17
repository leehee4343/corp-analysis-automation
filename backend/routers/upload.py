from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from .. import storage
from ..excel.generator import generate_excel
from ..models import Company
from ..parser.grade_ocr import GradeResult, extract_grades
from ..parser.pdf_parser import parse_pdf

router = APIRouter(prefix="/api", tags=["upload"])

UPLOADS_DIR = Path(__file__).resolve().parents[2] / "uploads"


@router.post("/upload", response_model=Company)
async def upload_pdf(file: UploadFile):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드할 수 있습니다.")

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    dest = UPLOADS_DIR / file.filename
    dest.write_bytes(await file.read())

    try:
        parsed = parse_pdf(str(dest))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"PDF 파싱에 실패했습니다: {e}") from e

    try:
        grades = extract_grades(str(dest))
    except Exception:
        # Tesseract 미설치 등으로 OCR을 못 해도 텍스트 기반 데이터는 그대로 등록한다.
        grades = GradeResult()

    company = storage.build_company(parsed, grades)
    storage.save_company(company)
    generate_excel(company)
    return company
