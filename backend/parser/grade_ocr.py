"""신용등급/EW등급/기업성장등급 게이지 이미지 OCR.

2페이지에 세 개의 게이지 그래픽이 왼쪽부터 [기업신용등급, EW등급, 기업성장등급] 순서로
배치되어 있고(큰 두 개는 318x159, 성장등급은 129x124 — 로고 배지(129x29)와 높이로 구분),
값이 텍스트 레이어가 아니라 이미지에 렌더링되어 있어 OCR이 필요하다. (PLAN.md Phase 1 참고)

게이지 하단 텍스트 주변에 색깔 있는 아치(진행률 표시)가 있어 그대로 OCR하면 오인식이
심하다. 텍스트는 항상 무채색(검정)이고 아치는 유채색이므로, 채도가 낮고 어두운 픽셀만
남기는 방식으로 이진화한 뒤 OCR한다.

Tesseract-OCR 바이너리가 시스템에 설치되어 있어야 동작한다 (README.md 참고).
"""
from __future__ import annotations

import io
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import fitz
import pytesseract
from PIL import Image

MIN_GAUGE_HEIGHT = 50
GAUGE_ORDER = ("credit_grade", "ew_grade", "growth_grade")

# 게이지 이미지 내 텍스트가 위치한 대략적인 영역 (아치 아래쪽 중앙)
_CROP_BOX = (0.05, 0.5, 0.95, 0.98)  # (left, top, right, bottom) 비율
_UPSCALE = 3
_DARK_BRIGHTNESS_THRESHOLD = 110
_SATURATION_THRESHOLD = 25

_NO_VALUE_TOKENS = {"?", "", "-"}

# 관리자 권한 없이 설치한 언어 데이터(kor.traineddata)를 쓰기 위해 프로젝트 로컬
# .tessdata/ 를 우선 사용한다 (setup_tessdata.py로 생성, README.md 참고).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_LOCAL_TESSDATA = _PROJECT_ROOT / ".tessdata"
if _LOCAL_TESSDATA.is_dir():
    os.environ["TESSDATA_PREFIX"] = str(_LOCAL_TESSDATA)

if not pytesseract.pytesseract.tesseract_cmd or pytesseract.pytesseract.tesseract_cmd == "tesseract":
    found = shutil.which("tesseract")
    if not found:
        default_win_path = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        if default_win_path.exists():
            found = str(default_win_path)
    if found:
        pytesseract.pytesseract.tesseract_cmd = found


def _gauge_pixmaps_on_page(page: "fitz.Page") -> list["fitz.Pixmap"]:
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


def _isolate_dark_neutral_text(img_rgb: Image.Image) -> Image.Image:
    """유채색(게이지 아치)을 지우고 어두운 무채색(텍스트)만 검게 남긴다."""
    px = img_rgb.load()
    w, h = img_rgb.size
    out = Image.new("L", (w, h), 255)
    out_px = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y][:3]
            brightness = (r + g + b) / 3
            saturation = max(r, g, b) - min(r, g, b)
            if brightness < _DARK_BRIGHTNESS_THRESHOLD and saturation < _SATURATION_THRESHOLD:
                out_px[x, y] = 0
    return out


def _preprocess_gauge(pix: "fitz.Pixmap") -> Image.Image:
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    w, h = img.size
    left, top, right, bottom = _CROP_BOX
    crop = img.crop((int(w * left), int(h * top), int(w * right), int(h * bottom)))
    bw = _isolate_dark_neutral_text(crop)
    return bw.resize((bw.width * _UPSCALE, bw.height * _UPSCALE), Image.LANCZOS)


def _ocr(img: Image.Image, lang: str, psm: int = 6) -> str:
    text = pytesseract.image_to_string(img, lang=lang, config=f"--psm {psm}").strip()
    return text.replace(" ", "")


def _read_credit_grade(pix: "fitz.Pixmap") -> str | None:
    """신용등급은 항상 영문+기호 (예: bb+, BBB-, AAA)."""
    img = _preprocess_gauge(pix)
    text = _ocr(img, lang="eng")
    return None if text in _NO_VALUE_TOKENS else text


def _read_korean_grade(pix: "fitz.Pixmap") -> str | None:
    """EW등급/기업성장등급은 값이 없으면 "?", 있으면 한글 단어(예: 정상, 우수)."""
    img = _preprocess_gauge(pix)
    no_value = _ocr(img, lang="eng")
    if no_value in _NO_VALUE_TOKENS:
        return None
    text = _ocr(img, lang="kor")
    return text if text and text not in _NO_VALUE_TOKENS else None


@dataclass
class GradeResult:
    credit_grade: str | None = None
    ew_grade: str | None = None
    growth_grade: str | None = None


def extract_grades(path: str, detail_page_index: int = 1) -> GradeResult:
    doc = fitz.open(path)
    result = GradeResult()
    if doc.page_count > detail_page_index:
        pixmaps = _gauge_pixmaps_on_page(doc[detail_page_index])
        readers = [_read_credit_grade, _read_korean_grade, _read_korean_grade]
        for key, pix, reader in zip(GAUGE_ORDER, pixmaps, readers):
            setattr(result, key, reader(pix))
    doc.close()
    return result
