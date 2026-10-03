from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile

from .. import storage
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

    if not parsed.business_no or not parsed.company_name:
        # 기업종합보고서가 아닌 PDF 등 — 사업자번호 없이 저장하면 빈 키의 기업이 생긴다
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail="사업자번호나 기업명을 찾지 못했습니다. CRETOP·KODATA 기업종합보고서 PDF인지 확인해 주세요.")

    try:
        company = storage.build_company(parsed, grades)
        storage.save_company(company)
        storage.save_source_pdf(company.business_no, dest.name, content)
        if project_id is not None:
            storage.add_companies_to_project(project_id, [company.business_no])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"데이터 저장 중 오류가 발생했습니다: {e}") from e
    if storage.uses_object_storage():
        # 원본은 Storage에 보관됐으므로 작업용 사본은 지운다(서버 디스크에 쌓이지 않게). SQLite 모드는 이 파일이 원본.
        dest.unlink(missing_ok=True)
    # 엑셀 보고서는 다운로드할 때 만든다(업로드 때 미리 만들면 outputs/에 파일만 쌓임)
    return company
