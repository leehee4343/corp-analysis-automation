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

import difflib
import io
import os
import re
import shutil
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import fitz
import pytesseract
from PIL import Image, ImageOps

MIN_GAUGE_HEIGHT = 50
GAUGE_ORDER = ("credit_grade", "ew_grade", "growth_grade")

# 게이지 이미지 내 텍스트가 위치한 대략적인 영역 (아치 아래쪽 중앙)
_CROP_BOX = (0.05, 0.5, 0.95, 0.98)  # (left, top, right, bottom) 비율
_UPSCALE = 3
_DARK_BRIGHTNESS_THRESHOLD = 110
_SATURATION_THRESHOLD = 25

_NO_VALUE_TOKENS = {"?", "", "-"}

# KIS/KODATA 신용등급 표기(예: bb+, bbb-, b0, aaa). 65개 실제 PDF로 배치 테스트해보니
# 색상 아치 잔여 노이즈 때문에 이 형식에 안 맞는 오인식이 다수 발생 — 형식 검증 후
# 여러 PSM 모드로 재시도하고, 그래도 안 맞으면 None(=검증 대기열行). (PLAN.md Phase 7 로그 참고)
_VALID_CREDIT_GRADE_RE = re.compile(r"^(aaa|aa|a|bbb|bb|b|ccc|cc|c|d)[+\-0]?$")
_CREDIT_GRADE_PSM_CANDIDATES = (6, 7, 8, 11)

# EW등급/기업성장등급(예: 정상, 유보)은 아치 이진화 잔여물이 글자 앞에 붙는 오인식이
# 있었다(예: "가\n유보" — 실제 값은 "유보"). 가장 긴 한글 연속 구간을 값으로 취급하고,
# 너무 짧으면(1글자) 노이즈로 보고 버린다.
_HANGUL_RUN_RE = re.compile(r"[가-힣]+")

# 관리자 권한 없이 설치한 언어 데이터(kor.traineddata)를 쓰기 위해 프로젝트 로컬
# .tessdata/ 를 우선 사용한다 (setup_tessdata.py로 생성, README.md 참고).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_LOCAL_TESSDATA = _PROJECT_ROOT / ".tessdata"
if _LOCAL_TESSDATA.is_dir():
    os.environ["TESSDATA_PREFIX"] = str(_LOCAL_TESSDATA)

if not pytesseract.pytesseract.tesseract_cmd or pytesseract.pytesseract.tesseract_cmd == "tesseract":
    found = shutil.which("tesseract")
    if not found:
        # PATH에 없을 때의 기본 설치 위치: Windows 공식 설치, macOS 사용자 폴더(conda-forge)·Homebrew
        candidates = [
            Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
            Path.home() / ".local" / "bin" / "tesseract",
            Path("/opt/homebrew/bin/tesseract"),
            Path("/usr/local/bin/tesseract"),
        ]
        found = next((str(p) for p in candidates if p.exists()), None)
    if found:
        pytesseract.pytesseract.tesseract_cmd = found


# 게이지는 318x159(2:1)·129x124(정사각형에 가까움). 페이지 상단 로고 배지(422x130, 약 3.2:1)는 제외.
_MAX_GAUGE_ASPECT = 2.2


def _gauge_pixmaps_on_page(page: "fitz.Page") -> list["fitz.Pixmap"]:
    infos = [i for i in page.get_image_info(xrefs=True)
             if i["height"] >= MIN_GAUGE_HEIGHT and i["width"] / i["height"] <= _MAX_GAUGE_ASPECT]
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
    """공백만 제거하고 줄바꿈은 남긴다 — 서로 다른 텍스트 조각(노이즈/실제 값)을
    구분하는 경계로 쓴다 (예: "가\\n유보")."""
    text = pytesseract.image_to_string(img, lang=lang, config=f"--psm {psm}").strip()
    return text.replace(" ", "")


# --- 신용등급: 여러 전처리·PSM 결과의 다수결 + 게이지 아치 색 교차검증 ---
# 단일 OCR은 조용히 틀린 값을 냈다(2026-10-01 65건 점검): 'a'→'d' 3건(부도 등급으로 오기록),
# 'aa-'→'aa' 1건. 그래서 (1) 크롭 2종 × 확대 3종 × PSM 3종 결과를 투표하고, (2) 게이지 아치 색이
# 등급 구간과 맞지 않는 후보는 버리며, (3) 가는 '-'/'+'를 놓친 후보보다 기호가 붙은 후보를 우선한다.
_CREDIT_ORDER = ["aaa", "aa+", "aa", "aa-", "a+", "a", "a-", "bbb+", "bbb", "bbb-", "bb+", "bb", "bb-",
                 "b+", "b", "b-", "ccc+", "ccc", "ccc-", "cc", "c", "d"]
# 아치 색 → 그 색으로 표시되는 등급 구간. 파랑/초록/노랑/주황 경계는 65건 실측
# (aa-=파랑, a·bbb+=초록, bbb~b+=노랑, b=주황), 측정되지 않은 등급은 순서상 인접 구간으로 포함.
_ARC_COLOR_BANDS = {
    (0, 120, 220): {"aaa", "aa+", "aa", "aa-"},
    (110, 170, 100): {"a+", "a", "a-", "bbb+"},
    (250, 200, 20): {"bbb", "bbb-", "bb+", "bb", "bb-", "b+"},
    (250, 120, 50): {"b", "b-", "ccc+", "ccc", "ccc-", "cc", "c", "d"},
}
_ARC_COLOR_TOLERANCE = 60
_CREDIT_CROPS = ((0.05, 0.5, 0.95, 0.98), (0.2, 0.45, 0.8, 0.95))
_CREDIT_UPSCALES = (2, 3, 4)
_CREDIT_PSMS = (7, 8, 6)
_CREDIT_WHITELIST = "-c tessedit_char_whitelist=abcdABCD+-0"


def _arc_band(img_rgb: Image.Image) -> set[str] | None:
    """게이지 아치 시작점(왼쪽 아래) 근처의 채도 높은 픽셀 평균색으로 등급 구간을 판정. 모르면 None."""
    w, h = img_rgb.size
    px = [img_rgb.getpixel((x, y)) for x in range(int(w * .08), int(w * .16)) for y in range(int(h * .80), int(h * .95))]
    sat = [p[:3] for p in px if max(p[:3]) - min(p[:3]) > 60]
    if not sat:
        return None
    avg = tuple(sum(c[i] for c in sat) / len(sat) for i in range(3))
    ref, dist = min(((r, sum((a - b) ** 2 for a, b in zip(avg, r)) ** .5) for r in _ARC_COLOR_BANDS), key=lambda x: x[1])
    return _ARC_COLOR_BANDS[ref] if dist <= _ARC_COLOR_TOLERANCE else None


def _credit_votes(img_rgb: Image.Image) -> Counter:
    votes: Counter = Counter()
    w, h = img_rgb.size
    for left, top, right, bottom in _CREDIT_CROPS:
        bw = _isolate_dark_neutral_text(img_rgb.crop((int(w * left), int(h * top), int(w * right), int(h * bottom))))
        for up in _CREDIT_UPSCALES:
            big = ImageOps.expand(bw.resize((bw.width * up, bw.height * up), Image.LANCZOS), border=20, fill=255)
            for psm in _CREDIT_PSMS:
                text = pytesseract.image_to_string(big, lang="eng", config=f"--psm {psm} {_CREDIT_WHITELIST}")
                text = text.strip().replace(" ", "").lower()
                if _VALID_CREDIT_GRADE_RE.match(text):
                    votes[text] += 1
    return votes


def _choose_credit_grade(votes: Counter, band: set[str] | None) -> str | None:
    candidates = [(g, n) for g, n in votes.most_common() if band is None or g in band]
    if not candidates:
        return None
    best, best_n = candidates[0]
    if best[-1] not in "+-0":  # 가는 기호를 놓친 경우: 같은 글자 + 기호 후보가 충분히 나오면 그쪽
        for g, n in candidates[1:]:
            if g[:-1] == best and g[-1] in "+-" and n >= 0.3 * best_n:
                return g
    return best


def _read_credit_grade(pix: "fitz.Pixmap") -> str | None:
    """신용등급은 항상 영문+기호 (예: bb+, bbb-, aaa). 값이 없으면("?") None."""
    img = _preprocess_gauge(pix)
    if _ocr(img, lang="eng", psm=_CREDIT_GRADE_PSM_CANDIDATES[0]).lower() in _NO_VALUE_TOKENS:
        return None
    raw = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    return _choose_credit_grade(_credit_votes(raw), _arc_band(raw))


# --- EW등급: OCR 결과를 알려진 값으로 보정 ---
# 실측 값: 정상·관심·유보. OCR이 '관심'을 '과시'로 읽은 사례가 있어(받침 누락), 자모 단위로 가장
# 가까운 알려진 값에 맞춘다. 충분히 가깝지 않으면 읽은 그대로 둔다(storage가 형식 의심 이슈로 표시).
_KNOWN_EW_GRADES = ("정상", "관심", "유보")


def _jamo(s: str) -> str:
    out = []
    for ch in s:
        code = ord(ch) - 0xAC00
        if 0 <= code < 11172:
            out += [chr(0x1100 + code // 588), chr(0x1161 + (code % 588) // 28)]
            if code % 28:
                out.append(chr(0x11A7 + code % 28))
        else:
            out.append(ch)
    return "".join(out)


def _normalize_ew(text: str | None) -> str | None:
    if not text or text in _KNOWN_EW_GRADES:
        return text
    scored = [(difflib.SequenceMatcher(None, _jamo(text), _jamo(k)).ratio(), k) for k in _KNOWN_EW_GRADES]
    score, best = max(scored)
    return best if score >= 0.7 else text


def _read_korean_grade(pix: "fitz.Pixmap") -> str | None:
    """EW등급/기업성장등급은 값이 없으면 "?", 있으면 한글 단어(예: 정상, 유보)."""
    img = _preprocess_gauge(pix)
    no_value = _ocr(img, lang="eng")
    if no_value in _NO_VALUE_TOKENS:
        return None
    text = _ocr(img, lang="kor")
    runs = _HANGUL_RUN_RE.findall(text)
    if not runs:
        return None
    longest = max(runs, key=len)
    return longest if len(longest) >= 2 else None


@dataclass
class GradeResult:
    credit_grade: str | None = None
    ew_grade: str | None = None
    growth_grade: str | None = None


def _grade_page_index(doc: "fitz.Document") -> int | None:
    """게이지가 있는 상세 페이지. 보통 2페이지지만 앞에 페이지가 하나 더 붙은 보고서는 3페이지라
    (예: 토리팜에프디·현진식품) "기업신용등급" 라벨이 있는 첫 페이지로 찾는다."""
    for i, page in enumerate(doc):
        if "기업신용등급" in page.get_text():
            return i
    return None


def extract_grades(path: str, detail_page_index: int | None = None) -> GradeResult:
    doc = fitz.open(path)
    result = GradeResult()
    if detail_page_index is None:
        detail_page_index = _grade_page_index(doc)
    if detail_page_index is not None and doc.page_count > detail_page_index:
        pixmaps = _gauge_pixmaps_on_page(doc[detail_page_index])
        readers = [_read_credit_grade, _read_korean_grade, _read_korean_grade]
        for key, pix, reader in zip(GAUGE_ORDER, pixmaps, readers):
            setattr(result, key, reader(pix))
        result.ew_grade = _normalize_ew(result.ew_grade)
    doc.close()
    return result
