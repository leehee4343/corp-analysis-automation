# 기업분석 자동화 시스템

CRETOP·KODATA 기업종합보고서 PDF를 등록하면 자동으로 파싱 → 엑셀 생성 → 웹 대시보드에 반영되는 로컬 전용 시스템입니다. (LLM API 미사용)

개발 진행 상황과 작업 절차는 [PLAN.md](./PLAN.md) 참고.

## 빠른 시작 (Windows)

**`프로그램 시작.bat`을 더블클릭하세요.** (`run.bat`도 동일하게 동작하는 같은 실행 파일입니다.) 처음 실행할 때 필요한 것들(가상환경, 패키지, 한국어 OCR 데이터)을 자동으로 준비하고, 잠시 후 브라우저가 자동으로 열립니다. 창을 닫으면(또는 그 안에서 Ctrl+C) 서버가 종료됩니다.

Tesseract-OCR 엔진 자체는 자동 설치되지 않습니다 — 처음 한 번은 아래 "Tesseract-OCR" 절의 1번을 직접 실행해야 합니다.

## 수동 설치 (직접 실행하고 싶을 때)

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

### Tesseract-OCR (신용등급 등 이미지 값 인식용, 별도 설치 필요)

기업신용등급/EW등급/기업성장등급이 PDF 안에서 텍스트가 아니라 게이지 이미지로 렌더링되어 있어 OCR이 필요합니다.

1. Tesseract-OCR 엔진 설치: `winget install --id UB-Mannheim.TesseractOCR -e` (또는 [공식 설치파일](https://github.com/UB-Mannheim/tesseract/wiki))
2. 한국어 언어 데이터 준비: `python setup_tessdata.py` — 관리자 권한 없이 설치한 경우 Tesseract 설치 폴더에 언어 데이터를 추가할 수 없어, 프로젝트 로컬 `.tessdata/`에 별도로 받아둡니다. `backend/parser/grade_ocr.py`가 이 폴더를 자동으로 인식합니다.

`pytesseract`는 Tesseract 바이너리를 감싸는 래퍼일 뿐이라 위 1번을 건너뛰면 동작하지 않습니다. 설치를 건너뛰어도 나머지 기능(기본정보/재무제표/재무진단 등)은 정상 동작하고, 신용등급만 "검증 대기"로 표시됩니다.

## 실행

```bash
uvicorn backend.app:app --reload
```

브라우저에서 http://127.0.0.1:8000 접속. `--reload`는 코드 변경 시 자동 재시작(개발용) — 평소 사용은 `run.bat` 또는 이 옵션 없이 실행하면 됩니다.

과거 버전(`data/*.json` 파일 저장 방식)에서 SQLite로 넘어온 경우, 기존 JSON 파일을 한 번 `python migrate_json_to_sqlite.py`로 옮겨주세요. 원본 JSON은 삭제하지 않으니 이관 결과를 확인한 뒤 필요하면 직접 정리하면 됩니다.

## 사용 방법

1. **PDF 업로드** 메뉴에서 CRETOP·KODATA 기업종합보고서 PDF를 끌어다 놓거나 선택하면 자동으로 파싱 → 저장 → 엑셀 생성까지 처리됩니다.
2. **대시보드**에서 전체 등록 현황(업종별/신용등급별 분포, 최근 등록 기업)을 확인합니다.
3. **기업 목록**에서 검색·필터(업종/신용등급/매출액)로 원하는 기업을 찾고, 상세 보기나 엑셀 다운로드를 할 수 있습니다.
4. **우편발송용 목록**에서 등록된 기업의 우편번호·주소·상호명·대표자를 우편번호순으로 확인하고, 엑셀로 내려받아 우편 발송에 바로 사용할 수 있습니다.
5. 필드 누락·형식 의심·중복 의심 등 자동으로 확신할 수 없는 값은 **데이터 검증** 메뉴에 모입니다. "직접 수정" 버튼으로 값을 고치면 해당 이슈가 자동으로 해제됩니다.
6. 각 기업 상세 페이지에서 "엑셀 다운로드"로 `outputs/{기업명}_기업종합보고서.xlsx`를 받거나, "원본 PDF 보기"로 업로드했던 원본을 다시 확인할 수 있습니다.

## 폴더 구조

```
프로그램 시작.bat    더블클릭 실행용 스크립트 (Windows) — run.bat과 내용 동일(의도적 중복, 아래 참고)
run.bat              위와 동일한 실행 스크립트
backend/             FastAPI 백엔드
  app.py               진입점 (프론트엔드 서빙 + API 라우터)
  routers/             API 엔드포인트 (companies, upload, validation)
  parser/              PDF 텍스트 파싱(PyMuPDF) + 신용등급 등 OCR(Tesseract)
  excel/               엑셀 보고서 생성 (openpyxl)
  models.py            데이터 스키마 (pydantic)
  storage.py           SQLite 저장/조회 + 검증 이슈 판정
frontend/index.html  웹 대시보드 (바닐라 HTML/CSS/JS, API 연동)
data/                회사별 파싱 결과 SQLite DB (companies.db)
uploads/              업로드된 원본 PDF
outputs/              생성된 엑셀 파일
tests/                pytest 테스트 + 샘플 PDF (샘플 PDF는 민감정보라 git 미포함)
```

## 테스트

```bash
pytest
```

일부 테스트는 `tests/sample_pdfs/`에 실제 PDF 샘플이 있어야 실행됩니다(민감정보라 git에는 없음 — 없으면 자동으로 skip). PLAN.md Phase 1/7 로그에 어떤 샘플을 어디서 복사해왔는지 기록되어 있습니다.
