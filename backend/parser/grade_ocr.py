"""신용등급/EW등급/기업성장등급 게이지 이미지 OCR.

2페이지에 세 개의 게이지 그래픽이 왼쪽부터 [기업신용등급, EW등급, 기업성장등급] 순서로
배치되어 있고(큰 두 개는 318x159, 성장등급은 129x124 — 로고 배지(129x29)와 높이로 구분),
값이 텍스트 레이어가 아니라 이미지에 렌더링되어 있어 OCR이 필요하다. (PLAN.md Phase 1 참고)

Tesseract-OCR 바이너리가 시스템에 설치되어 있어야 동작한다 (README.md 참고).
"""
from __future__ import annotations

import io
from dataclasses import dataclass

import fitz
import pytesseract
from PIL import Image

MIN_GAUGE_HEIGHT = 50
GAUGE_ORDER = ("credit_grade", "ew_grade", "growth_grade")

# OCR 오인식/값없음("?") 필터용
_NO_VALUE_TOKENS = {"?", "", "-"}


def _gauge_images_on_page(page: "fitz.Page") -> list["fitz.Pixmap"]:
    infos = [i for i in page.get_image_info(xrefs=True) if i["height"] >= MIN_GAUGE_HEIGHT]
    infos.sort(key=lambda i: i["bbox"][0])
    doc = page.parent
    pixmaps = []
    for info in infos:
        pix = fitz.Pixmap(doc, info["xref"])
        if pix.n - pix.alpha >= 4:
            pix = fitz.Pixmap(fitz.csRGB, pix)
        pixmaps.append(pix)
    return pixmaps


def _ocr_gauge(pix: "fitz.Pixmap") -> str | None:
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    text = pytesseract.image_to_string(img, lang="kor+eng", config="--psm 7").strip()
    text = text.replace(" ", "")
    if text in _NO_VALUE_TOKENS:
        return None
    return text


@dataclass
class GradeResult:
    credit_grade: str | None = None
    ew_grade: str | None = None
    growth_grade: str | None = None


def extract_grades(path: str, detail_page_index: int = 1) -> GradeResult:
    doc = fitz.open(path)
    result = GradeResult()
    if doc.page_count > detail_page_index:
        page = doc[detail_page_index]
        pixmaps = _gauge_images_on_page(page)
        for key, pix in zip(GAUGE_ORDER, pixmaps):
            setattr(result, key, _ocr_gauge(pix))
    doc.close()
    return result
