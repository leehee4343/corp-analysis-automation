# 기업분석 자동화 시스템 — 개발 작업계획

> 이 문서는 Claude Code, Codex CLI, Gemini CLI 등 **어떤 AI 코딩 도구로 이어서 작업하더라도** 동일하게 참조할 수 있는 단일 진행 문서입니다.
> 토큰/세션이 끊기면 다른 도구가 이 파일을 열어 체크박스 상태와 "진행 로그"만 보고 이어서 작업할 수 있어야 합니다.

- 작성일: 2026-08-17
- 원본 목업: `index.html` (정적 프로토타입, 하드코딩 데이터)
- 목표: 목업의 UI/흐름을 유지하면서 실제 PDF 파싱 → 데이터 저장 → 엑셀 생성 → 대시보드 반영이 동작하는 로컬 시스템 구축

---

## 0. 절대 원칙 (제약사항)

- **로컬 전용, LLM API 미사용.** 목업 하단 상태바에 반복 명시됨 — 파싱은 규칙/라벨 기반으로만 수행. 이 제약을 바꾸려면 사용자 확인 필요.
- PDF 형식은 **CRETOP / KODATA 기업종합보고서**로 한정.
- 기존 `index.html`의 화면 구조·디자인 토큰(색상, 레이아웃)은 최대한 유지하고, 하드코딩된 부분만 실데이터 연동으로 교체.

---

## 1. 기술 스택 (가정 — 확인 필요 ⚠️)

| 영역 | 선택 | 근거 |
|---|---|---|
| 백엔드 | Python 3.11+ / FastAPI + Uvicorn | 목업 로그에 `pdfplumber`, `openpyxl` 언급되어 Python 기반 암시. FastAPI는 로컬 단일 사용자 도구에 가볍고 자동 문서화(`/docs`) 제공 |
| PDF 파싱 | `pdfplumber` | 목업 로그에 명시됨 |
| 엑셀 생성 | `openpyxl` | 목업 로그에 명시됨 |
| 데이터 저장 | 회사별 JSON 파일 (`data/{사업자번호}.json`) | 목업 로그의 `JSON 저장 → data/옥산농원.json`과 일치. 규모(~128개사) 상 DB 불필요, 추후 검색 성능 이슈 시 SQLite 인덱스 추가 검토 |
| 프론트엔드 | 기존 `index.html`(바닐라 HTML/CSS/JS) 유지, `fetch()`로 API 연동 | 프레임워크 도입은 이 도구의 규모에 비해 과함 |

> ⚠️ **사용자 확인 필요**: 위 스택은 목업 코드에서 유추한 가정입니다. 다르게 가고 싶다면 이 표를 수정하고 아래 "결정 사항 & 이슈"에 기록하세요.

---

## 2. 폴더 구조 (목표)

```
20260817_강수찬 영업 지원 프로젝트/
├── PLAN.md                      # 이 파일
├── README.md                    # 설치/실행 방법
├── requirements.txt
├── .gitignore
├── backend/
│   ├── app.py                   # FastAPI 진입점
│   ├── models.py                # pydantic 데이터 스키마
│   ├── storage.py                # JSON 저장/조회
│   ├── parser/
│   │   ├── labels.py            # 라벨 앵커 · 정규식 정의
│   │   └── pdf_parser.py        # pdfplumber 기반 파싱 로직
│   ├── excel/
│   │   └── generator.py         # openpyxl 기반 엑셀 생성
│   └── routers/
│       ├── companies.py
│       ├── upload.py
│       └── validation.py
├── data/                         # 회사별 파싱 결과 JSON
├── uploads/                      # 원본 PDF 보관
├── outputs/                      # 생성된 엑셀 파일
├── frontend/
│   └── index.html                # 기존 목업 → 실데이터 연동판
└── tests/
    └── sample_pdfs/               # 테스트용 실제 PDF 샘플
```

---

## 3. 단계별 작업 (Phase)

체크박스는 완료 시 `- [x]`로 바꾸고, 담당 도구/날짜를 뒤에 `(Claude, 2026-08-18)` 형식으로 덧붙입니다.

### Phase 0 — 프로젝트 기반 설정
- [x] git 저장소 초기화 + `.gitignore` (venv, data/, uploads/, outputs/ 등 제외) (Claude, 2026-08-17)
- [x] 폴더 구조 생성 (backend/, data/, uploads/, outputs/, frontend/, tests/) (Claude, 2026-08-17)
- [x] `requirements.txt` 작성 (fastapi, uvicorn, pdfplumber, openpyxl, python-multipart, pydantic) (Claude, 2026-08-17)
- [x] 기존 `index.html` → `frontend/index.html`로 이동 (Claude, 2026-08-17)
- [x] `README.md` 초안 (설치/실행 방법) (Claude, 2026-08-17)

### Phase 1 — 샘플 PDF 확보 & 라벨 규칙 정의
- [ ] 실제 CRETOP/KODATA 기업종합보고서 PDF 샘플 최소 2~3개 확보 (양계업, 농업법인 등 업종 다양화)
- [ ] PDF 구조 분석 (페이지 레이아웃, 표 구조, 라벨 위치가 문서마다 고정적인지 확인)
- [ ] 전체 추출 필드 목록 확정 (기업명, 사업자번호, 대표자, 주소, 설립일, 업종, 기업신용등급, EW등급, 기업규모, 재무3개년 등 — 목업의 "필드 매핑 규칙" 표를 기준으로 확장)
- [ ] 라벨 앵커 · 정규식 정의 (`backend/parser/labels.py`)

### Phase 2 — PDF 파싱 엔진
- [ ] pdfplumber 텍스트/표 추출 모듈
- [ ] 라벨 기반 기본정보 필드 매칭
- [ ] 재무상태표·손익계산서 3개년 표 파싱
- [ ] 파싱 실패/누락 필드 감지 → 검증 대기열 후보로 마킹
- [ ] 샘플 PDF 기준 파싱 정확도 테스트

### Phase 3 — 데이터 저장 & 스키마
- [ ] 회사 데이터 pydantic 모델 확정
- [ ] `data/{사업자번호}.json` 저장/조회 함수
- [ ] 검증 이슈 저장 구조 (필드 누락/형식 의심/중복 의심)

### Phase 4 — 엑셀 자동 생성
- [ ] openpyxl 템플릿 작성 (기존 CRETOP/KODATA 보고서 양식 참고)
- [ ] JSON → 엑셀 매핑 함수
- [ ] `outputs/{기업명}_기업종합보고서.xlsx` 생성 확인

### Phase 5 — 백엔드 API
- [ ] FastAPI 앱/라우터 골격
- [ ] `POST /upload` (PDF 업로드 → 파싱 → JSON 저장 → 엑셀 생성)
- [ ] `GET /companies` (검색/필터/페이지네이션)
- [ ] `GET /companies/{id}` (상세)
- [ ] `GET /companies/{id}/excel` (다운로드)
- [ ] `GET /issues` (검증 대기열)
- [ ] `PATCH /companies/{id}` (수동 수정)
- [ ] `GET /dashboard/summary` (KPI·업종별·등급별 통계)

### Phase 6 — 프론트엔드 실데이터 연동
- [ ] 대시보드 하드코딩 데이터 → `fetch()` API 연동
- [ ] 기업 목록 페이지 검색/필터/페이지네이션 실연동
- [ ] 업로드 드롭존 → 실제 파일 업로드 + 진행 상태 표시
- [ ] 처리 로그 콘솔 → 백엔드 로그 폴링/스트리밍
- [ ] 검증 대기열 화면 → issues API 연동 + 수동 수정 폼

### Phase 7 — 테스트 & 품질 검증
- [ ] 실제 PDF로 End-to-End 테스트 (업로드→파싱→엑셀→대시보드)
- [ ] 파싱 실패 케이스 → 검증 대기열 정상 등록 확인
- [ ] 브라우저 수동 전체 플로우 테스트

### Phase 8 — 실행/배포 준비
- [ ] 로컬 실행 스크립트 (`run.bat` 등)
- [ ] README 정리 (설치/실행/폴더 설명)
- [ ] (선택) 사용자 매뉴얼

---

## 4. 협업 규칙 (Claude / Codex / Gemini 병행 진행)

1. 작업 시작 전 이 파일을 열어 체크박스 상태를 확인 — 이미 진행 중이거나 완료된 항목 중복 작업 금지.
2. 완료한 항목은 즉시 `- [x] ... (도구명, 날짜)`로 갱신.
3. 진행 중 발견한 이슈, 방향 전환, 사용자 결정 사항은 아래 "5. 결정 사항 & 이슈"에 append.
4. 가능하면 **Phase 단위로 순차 진행** — 여러 도구가 동시에 같은 Phase/같은 파일을 건드리지 않도록 조율(각자 시작 전 이 파일의 최신 상태를 다시 읽을 것).
5. git 저장소가 준비되면(Phase 0) 도구별로 작업 후 커밋 — 커밋 메시지에 어떤 Phase 항목을 처리했는지 명시.

---

## 5. 결정 사항 & 이슈 로그

> 새 항목은 맨 아래에 날짜순으로 추가.

- 2026-08-17 (Claude): 초기 작업계획 수립. 기술 스택은 목업 코드(pdfplumber/openpyxl 언급)에서 유추한 가정이며 사용자 확정 필요.
- 2026-08-17 (Claude): 사용자가 기술 스택 확정, Phase 0 진행 승인. git init, 폴더 구조, requirements.txt, README.md, index.html→frontend/ 이동 완료. Phase 1(샘플 PDF 확보)부터는 사용자의 실제 PDF 샘플이 필요.
