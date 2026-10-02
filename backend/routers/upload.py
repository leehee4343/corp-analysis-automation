from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from .. import storage
from ..excel.generator import generate_excel
from ..models import Company
from ..parser.grade_ocr import GradeResult, extract_grades
from ..parser.pdf_parser import parse_pdf
from ..paths import UPLOADS_DIR

router = APIRouter(prefix="/api", tags=["upload"])


@router.post("/upload", response_model=Company)
async def upload_pdf(file: UploadFile, project_id: int | None = None):
    """PDF 분석·저장 후 project_id 프로젝트의 참여 기업으로 등록한다(화면은 항상 프로젝트를 지정)."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="PDF 파일만 업로드할 수 있습니다.")
    if project_id is not None and storage.get_project(project_id) is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 프로젝트입니다.")

    try:
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        dest = UPLOADS_DIR / Path(file.filename).name  # 경로 조작 방지, 파일명만 사용
        content = await file.read()
        dest.write_bytes(content)
    except OSError as e:
        # 백신 실시간 검사 등이 방금 쓴 파일을 잠그는 경우 등 — 원인을 그대로 노출한다.
        raise HTTPException(status_code=500, detail=f"파일 저장에 실패했습니다: {e}") from e

    try:
        parsed = parse_pdf(str(dest))
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"PDF 파싱에 실패했습니다: {e}") from e

    try:
        grades = extract_grades(str(dest))
    except Exception:
        # Tesseract 미설치 등으로 OCR을 못 해도 텍스트 기반 데이터는 그대로 등록한다.
        grades = GradeResult()

    try:
        company = storage.build_company(parsed, grades)
        storage.save_company(company)
        storage.save_source_pdf(company.business_no, dest.name, content)
        if project_id is not None:
            storage.add_companies_to_project(project_id, [company.business_no])
        generate_excel(company)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터 저장/엑셀 생성 중 오류가 발생했습니다: {e}") from e

    return company
