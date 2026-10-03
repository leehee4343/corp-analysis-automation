# 기업분석 자동화 시스템

CRETOP·KODATA 기업종합보고서 PDF를 올리면 내용을 규칙 기반으로 읽어(LLM 미사용) 데이터베이스에 저장하고,
대시보드·기업 목록·우편발송/법인형태별 목록·엑셀 보고서·영업 관리(DM 발송·승인/거절·메모)를 제공합니다.
모든 데이터는 **프로젝트(지원사업) 단위**로 관리합니다. 개발 기록은 [PLAN.md](./PLAN.md), 화면 규칙은 [DESIGN_GUIDE.md](./DESIGN_GUIDE.md),
데이터 저장 구조는 [docs/SUPABASE_STRUCTURE.md](./docs/SUPABASE_STRUCTURE.md)를 참고하세요.

## 실행

| 환경 | 방법 | 주소 |
|---|---|---|
| macOS | `프로그램 시작.command` 더블클릭 (처음 실행 때 uv로 Python 3.12 가상환경·패키지 자동 준비) | http://127.0.0.1:8700 |
| Windows | `프로그램 시작.bat` 더블클릭 (`run.bat`과 같음) | http://127.0.0.1:8000 |
| 배포 | GitHub `master`에 올리면 Render가 자동 배포 (`render.yaml`, `Dockerfile`) | https://corp-analysis-automation.onrender.com |

- 로그인: `APP_LOGIN_PASSWORD`(아이디 `APP_LOGIN_USER`, 기본 `admin`)가 설정돼 있으면 로그인 화면이 켜집니다. 오른쪽 위 `로그아웃`.
- 개발 중 서버 재시작(macOS): `tools/restart_local.sh` — 기존 서버와 빈 터미널 창을 정리하고 브라우저 탭을 새로 열지 않습니다.
- Render 무료 요금제는 한동안 접속이 없으면 잠들어 첫 접속이 수십 초 걸립니다(데이터는 Supabase에 있어 사라지지 않음).

## 데이터 저장

`.env`(git 제외)에 `DATABASE_URL` 등이 있으면 **Supabase**(Postgres `corp_analysis` 스키마 + Storage `corp-analysis` 버킷)를,
없으면 로컬 SQLite(`data/companies.db`)와 `uploads/` 폴더를 씁니다. 비밀 값은 코드·GitHub에 넣지 않습니다(저장소가 공개).

| 변수 | 용도 |
|---|---|
| `DATABASE_URL` | 앱 전용 DB 계정 연결 문자열 |
| `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `STORAGE_BUCKET`, `STORAGE_SERVICE_EMAIL`, `STORAGE_SERVICE_PASSWORD` | 원본 PDF 보관(Storage 서비스 계정) |
| `APP_LOGIN_USER`, `APP_LOGIN_PASSWORD` | 로그인·프로젝트 삭제 인증 |

## 메뉴

프로젝트 목록 · PDF 업로드 · 데이터 검증 · 대시보드 · 기업 목록 · 기업 데이터 활용 목록(우편발송용 목록, 개인사업자, 일반법인, 농업회사법인, 영농조합법인) · 영업 관리

- 프로젝트를 삭제하면(경고 → 아이디·비밀번호 확인) 그 프로젝트에만 있는 기업의 분석 정보·원본 PDF와 영업 기록이 모두 삭제됩니다.
- 기업·PDF를 삭제하면 그 기업의 모든 프로젝트 영업 기록도 함께 삭제됩니다.

## 신용등급 OCR (Tesseract)

신용등급·EW등급·성장등급은 PDF 안에서 이미지라 Tesseract-OCR이 필요합니다(macOS는 사용자 폴더 설치본 자동 인식, Windows는
`winget install --id UB-Mannheim.TesseractOCR -e` 후 `python setup_tessdata.py`). 없어도 나머지 데이터는 저장되고 등급만 '데이터 검증'에 모입니다.

## 폴더 구조

```
backend/
  app.py              진입점(화면·API·로그인)       auth_middleware.py  로그인 세션 쿠키
  routers/            API (companies, upload, pdfs, projects, sales, mailing, category_list, validation, export)
  parser/             PDF 해석(pdf_parser·sections), 등급 OCR(grade_ocr), 추출 완성도(coverage)
  storage.py          DB 저장·조회·검색·통계 (Postgres/SQLite)   object_storage.py  Supabase Storage
  excel/generator.py  기업별 엑셀 보고서·우편발송 목록
frontend/index.html   웹 화면(단일 파일)            frontend/login.html  로그인 화면
tools/restart_local.sh  macOS 개발용 재시작          tests/  pytest (샘플 PDF는 민감정보라 git 미포함)
```

## 테스트

```bash
.venv/bin/python -m pytest -q
```
테스트는 항상 임시 SQLite로 격리되어 실제 Supabase에 쓰지 않습니다.
