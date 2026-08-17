# 기업분석 자동화 시스템

CRETOP·KODATA 기업종합보고서 PDF를 등록하면 자동으로 파싱 → 엑셀 생성 → 웹 대시보드에 반영되는 로컬 전용 시스템입니다. (LLM API 미사용)

개발 진행 상황과 작업 절차는 [PLAN.md](./PLAN.md) 참고.

## 설치

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

### Tesseract-OCR (신용등급 등 이미지 값 인식용, 별도 설치 필요)

기업신용등급/EW등급/기업성장등급이 PDF 안에서 텍스트가 아니라 게이지 이미지로 렌더링되어 있어 OCR이 필요합니다.
[Tesseract-OCR](https://github.com/UB-Mannheim/tesseract/wiki) 설치 후 한국어 데이터(`kor`)가 포함됐는지 확인하세요. `pytesseract`는 이 바이너리를 감싸는 래퍼일 뿐이라 바이너리를 따로 설치하지 않으면 동작하지 않습니다.

## 실행

```bash
uvicorn backend.app:app --reload
```

> 백엔드(`backend/app.py`)는 아직 구현 전입니다 (PLAN.md Phase 5 참고).

## 폴더 구조

```
backend/    FastAPI 백엔드 (파싱, 엑셀 생성, API)
frontend/   웹 대시보드 (index.html)
data/       회사별 파싱 결과 JSON
uploads/    원본 PDF
outputs/    생성된 엑셀 파일
tests/      샘플 PDF 및 테스트
```
