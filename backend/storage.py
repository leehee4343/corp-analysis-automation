"""회사별 데이터 저장/조회 및 검증 이슈 판정.

저장소는 두 가지다:
- `DATABASE_URL` 환경변수가 있으면 Supabase personal-projects 프로젝트의 Postgres
  (`corp_analysis` 스키마, 전용 계정 corp_analysis_app). 원본 PDF 파일은 Storage 버킷
  `corp-analysis`(object_storage.py)에, 그 메타데이터는 source_pdfs 테이블에 둔다 — 서버가
  재시작·재배포되어도 데이터가 남는다. 구조 규칙은 docs/SUPABASE_STRUCTURE.md.
- 없으면 기존처럼 SQLite 한 파일(`paths.DB_PATH`) + uploads/ 폴더의 원본 PDF(테스트·오프라인용).

두 경우 모두 companies 테이블에 회사 하나당 행 하나(사업자번호가 고유키)이고, `data`
컬럼에 Company 전체를 JSON으로 저장한다. company_name/industry_name/credit_grade/status/
parsed_at은 DB 도구로 열어봐도 바로 보이도록 중복 저장하는 조회용 컬럼이다 — 필터링/정렬
자체는 여전히 호출 측(라우터)에서 파이썬으로 한다.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from . import object_storage
from .models import Company, CompanyListItem, CompanyUpdate, DiagnosisRatings, IndustryRank, ValidationIssue
from .parser.grade_ocr import GradeResult
from .parser.pdf_parser import ParsedCompany
from .paths import DB_PATH

_FIELD_LABELS_KO = {
    "business_no": "사업자번호",
    "company_name": "기업명",
    "representative": "대표자명",
    "address": "주소",
    "financials": "재무제표 요약",
}


def _pg_url() -> str | None:
    # 호출 시점에 읽는다 — 테스트가 환경변수를 지워 SQLite로 격리할 수 있어야 한다.
    return os.environ.get("DATABASE_URL") or None


def _pg_conn():
    import psycopg  # SQLite만 쓰는 환경에서는 필요 없도록 지연 임포트
    return psycopg.connect(_pg_url(), autocommit=True)


def _get_conn() -> sqlite3.Connection:
    # DB_PATH를 함수 안에서 읽어야 테스트의 monkeypatch(storage.DB_PATH)가 반영된다 —
    # 모듈 임포트 시점에 값을 미리 캡처해두면 갱신되지 않는다(admin.py에서 겪은 버그와 동일 유형).
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            region TEXT,
            start_date TEXT,
            end_date TEXT,
            status TEXT NOT NULL DEFAULT '진행중',
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS project_companies (
            project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            business_no TEXT NOT NULL,
            added_at TEXT NOT NULL,
            PRIMARY KEY (project_id, business_no)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sales_activities (
            project_id INTEGER NOT NULL,
            business_no TEXT NOT NULL,
            dm_sent INTEGER NOT NULL DEFAULT 0,
            dm_sent_at TEXT,
            decision TEXT CHECK (decision IN ('승인', '거절')),
            decided_at TEXT,
            updated_at TEXT NOT NULL,
            memo TEXT,
            memo_updated_at TEXT,
            PRIMARY KEY (project_id, business_no),
            FOREIGN KEY (project_id, business_no) REFERENCES project_companies (project_id, business_no) ON DELETE CASCADE
        )
    """)
    # 메모 열 추가(2026-10-02) 전에 만들어진 로컬 DB 보정
    sales_cols = {r[1] for r in conn.execute("PRAGMA table_info(sales_activities)")}
    for col in ("memo", "memo_updated_at"):
        if col not in sales_cols:
            conn.execute(f"ALTER TABLE sales_activities ADD COLUMN {col} TEXT")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            business_no TEXT PRIMARY KEY,
            company_name TEXT NOT NULL,
            industry_name TEXT,
            credit_grade TEXT,
            status TEXT NOT NULL,
            parsed_at TEXT NOT NULL,
            data TEXT NOT NULL
        )
    """)
    return conn


def _build_issues(parsed: ParsedCompany, grades: GradeResult) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    for error in parsed.parse_errors:
        issues.append(ValidationIssue(
            type="missing_field", field=None,
            message=f"일부 항목 파싱 중 오류가 발생해 건너뛰었습니다 ({error}). 원본 PDF에서 직접 확인하세요.",
        ))

    for key in parsed.missing_fields:
        label = _FIELD_LABELS_KO.get(key, key)
        issues.append(ValidationIssue(
            type="missing_field", field=key, message=f"'{label}' 값을 찾지 못했습니다."
        ))

    for key in parsed.cross_check_mismatch:
        label = _FIELD_LABELS_KO.get(key, key)
        issues.append(ValidationIssue(
            type="format_suspect", field=key,
            message=f"표지와 상세 페이지의 '{label}' 값이 서로 다릅니다.",
        ))

    if parsed.representative and any(ch.isdigit() for ch in parsed.representative):
        issues.append(ValidationIssue(
            type="format_suspect", field="representative",
            message="'대표자명' 필드에 숫자가 포함되어 있습니다. OCR 오인식 가능성이 있습니다.",
        ))

    if not parsed.balance_summary or not parsed.income_summary:
        issues.append(ValidationIssue(
            type="missing_field", field="financials",
            message="재무상태표/손익계산서 요약 값을 찾지 못했습니다. 표 구조를 확인하세요.",
        ))

    if not grades.credit_grade:
        issues.append(ValidationIssue(
            type="missing_field", field="credit_grade",
            message="기업신용등급 값을 인식하지 못했습니다 (게이지 이미지 OCR 실패 가능성). 원본 PDF에서 확인하세요.",
        ))

    if parsed.business_no:
        existing = load_company(parsed.business_no)
        if (
            existing
            and existing.report_query_datetime
            and parsed.report_query_datetime
            and existing.report_query_datetime != parsed.report_query_datetime
        ):
            issues.append(ValidationIssue(
                type="duplicate_suspect", field=None,
                message=(
                    f"동일 사업자번호로 {existing.report_query_datetime} 보고서가 이미 등록되어 "
                    "있습니다. 최신본으로 교체하시겠습니까?"
                ),
            ))

    return issues


def build_company(parsed: ParsedCompany, grades: GradeResult | None = None) -> Company:
    grades = grades or GradeResult()
    issues = _build_issues(parsed, grades)
    return Company(
        business_no=parsed.business_no or "",
        company_name=parsed.company_name or "",
        representative=parsed.representative,
        address=parsed.address,
        postal_code=parsed.postal_code,
        founded_date=parsed.founded_date,
        industry_code=parsed.industry_code,
        industry_name=parsed.industry_name,
        company_type=parsed.company_type,
        company_size=parsed.company_size,
        credit_grade=grades.credit_grade,
        ew_grade=grades.ew_grade,
        growth_grade=grades.growth_grade,
        balance_summary=parsed.balance_summary,
        income_summary=parsed.income_summary,
        ratio_summary=parsed.ratio_summary,
        diagnosis=DiagnosisRatings(**parsed.diagnosis),
        industry_rank=IndustryRank(**parsed.industry_rank),
        peer_comparison=parsed.peer_comparison,
        report_query_datetime=parsed.report_query_datetime,
        evaluation_date=parsed.evaluation_date,
        settlement_date=parsed.settlement_date,
        source_pdf=parsed.source_pdf,
        page_count=parsed.page_count,
        credit_info=parsed.credit_info,
        certifications=parsed.certifications,
        ip_rights=parsed.ip_rights,
        relationship_existence=parsed.relationship_existence,
        ledger_detail=parsed.ledger_detail,
        ratio_detail=parsed.ratio_detail,
        diagnosis_commentary=parsed.diagnosis_commentary,
        personal_info=parsed.personal_info,
        soft_sections=parsed.soft_sections,
        basic_extra=parsed.basic_extra,
        my_financial_data=parsed.my_financial_data,
        cash_flow_summary=parsed.cash_flow_summary,
        cash_flow_base_date=parsed.cash_flow_base_date,
        audit_opinions=parsed.audit_opinions,
        diagnosis_details=parsed.diagnosis_details,
        industry_rank_list=parsed.industry_rank_list,
        industry_top5=parsed.industry_top5,
        industry_base_year=parsed.industry_base_year,
        peer_base_year=parsed.peer_base_year,
        partners=parsed.partners,
        history=parsed.history,
        bid_summary=parsed.bid_summary,
        tech_info=parsed.tech_info,
        extraction_coverage=parsed.extraction_coverage,
        parsed_at=datetime.now(timezone.utc),
        issues=issues,
    )


_PG_UPSERT = """
    INSERT INTO companies (business_no, company_name, industry_name, credit_grade, status, parsed_at, data)
    VALUES (%s, %s, %s, %s, %s, %s, %s::json)
    ON CONFLICT (business_no) DO UPDATE SET
        company_name = excluded.company_name,
        industry_name = excluded.industry_name,
        credit_grade = excluded.credit_grade,
        status = excluded.status,
        parsed_at = excluded.parsed_at,
        data = excluded.data
"""


def save_company(company: Company) -> None:
    if _pg_url():
        with _pg_conn() as conn:
            conn.execute(_PG_UPSERT, (
                company.business_no, company.company_name, company.industry_name, company.credit_grade,
                company.status, company.parsed_at, company.model_dump_json(),
            ))
        return
    conn = _get_conn()
    with conn:
        conn.execute(
            """
            INSERT INTO companies (business_no, company_name, industry_name, credit_grade, status, parsed_at, data)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(business_no) DO UPDATE SET
                company_name=excluded.company_name,
                industry_name=excluded.industry_name,
                credit_grade=excluded.credit_grade,
                status=excluded.status,
                parsed_at=excluded.parsed_at,
                data=excluded.data
            """,
            (
                company.business_no,
                company.company_name,
                company.industry_name,
                company.credit_grade,
                company.status,
                company.parsed_at.isoformat(),
                company.model_dump_json(),
            ),
        )
    conn.close()


def load_company(business_no: str) -> Company | None:
    if _pg_url():
        with _pg_conn() as conn:
            row = conn.execute("SELECT data FROM companies WHERE business_no = %s", (business_no,)).fetchone()
        return Company.model_validate(row[0]) if row else None
    conn = _get_conn()
    row = conn.execute("SELECT data FROM companies WHERE business_no = ?", (business_no,)).fetchone()
    conn.close()
    if row is None:
        return None
    return Company.model_validate_json(row[0])


def delete_company(business_no: str) -> bool:
    """분석 데이터만 지운다 — 원본 PDF(uploads/ 또는 source_pdfs 테이블)는 남겨두므로
    다시 업로드하면 재등록된다."""
    if _pg_url():
        with _pg_conn() as conn:
            cursor = conn.execute("DELETE FROM companies WHERE business_no = %s", (business_no,))
        return cursor.rowcount > 0
    conn = _get_conn()
    with conn:
        cursor = conn.execute("DELETE FROM companies WHERE business_no = ?", (business_no,))
        conn.execute("DELETE FROM project_companies WHERE business_no = ?", (business_no,))  # Postgres는 FK cascade
    conn.close()
    return cursor.rowcount > 0


def list_companies(project_id: int | None = None) -> list[Company]:
    """전체 기업, 또는 project_id가 있으면 그 프로젝트의 참여 기업만."""
    where = " WHERE business_no IN (SELECT business_no FROM project_companies WHERE project_id = {p})" if project_id else ""
    if _pg_url():
        with _pg_conn() as conn:
            rows = conn.execute(f"SELECT data FROM companies{where.format(p='%s')} ORDER BY business_no",
                                (project_id,) if project_id else ()).fetchall()
        return [Company.model_validate(row[0]) for row in rows]
    conn = _get_conn()
    rows = conn.execute(f"SELECT data FROM companies{where.format(p='?')} ORDER BY business_no",
                        (project_id,) if project_id else ()).fetchall()
    conn.close()
    return [Company.model_validate_json(row[0]) for row in rows]


# ---------------------------------------------------------------------------
# 프로젝트 (지원사업 등): 기업 PDF는 프로젝트 단위로 등록한다. 기업과 다대다.
# ---------------------------------------------------------------------------
# 지역·상태는 입력받지 않는다(사용자 결정 2026-10-02). 상태는 지원기간으로 매번 계산하며, DB의 region·status 열은
# 다른 프로그램과의 호환을 위해 남겨 두기만 한다.
_PROJECT_FIELDS = ("name", "description", "start_date", "end_date")


def project_status(start_date, end_date, today: date | None = None) -> str:
    """지원기간 기준 상태: 시작 전 '준비', 기간 중 '진행중', 종료일 다음 날부터 '종료'. 날짜가 없는 쪽은 열린 기간으로 본다."""
    today = today or date.today()
    start, end = (str(d)[:10] if d else None for d in (start_date, end_date))
    if start and today.isoformat() < start:
        return "준비"
    if end and today.isoformat() > end:
        return "종료"
    return "진행중"


def _run(sql: str, params: tuple = (), *, fetch: str | None = None):
    """Postgres(%s)·SQLite(?) 공통 실행. fetch: None | 'one' | 'all'. 반환: (결과, 영향 행 수)."""
    if _pg_url():
        with _pg_conn() as conn:
            cur = conn.execute(sql, params)
            result = cur.fetchone() if fetch == "one" else cur.fetchall() if fetch == "all" else None
            return result, cur.rowcount
    conn = _get_conn()
    with conn:
        cur = conn.execute(sql.replace("%s", "?"), params)
        result = cur.fetchone() if fetch == "one" else cur.fetchall() if fetch == "all" else None
        rowcount = cur.rowcount
    conn.close()
    return result, rowcount


def _iso(value) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)


_PROJECT_SELECT = """
    SELECT p.id, p.name, p.description, p.start_date, p.end_date, p.created_at,
           (SELECT COUNT(*) FROM project_companies pc WHERE pc.project_id = p.id) AS company_count
    FROM projects p
"""


def _project_row(row) -> dict:
    keys = ("id", "name", "description", "start_date", "end_date", "created_at", "company_count")
    out = dict(zip(keys, row))
    for k in ("start_date", "end_date", "created_at"):
        out[k] = _iso(out[k])
    out["status"] = project_status(out["start_date"], out["end_date"])
    return out


def list_projects() -> list[dict]:
    rows, _ = _run(_PROJECT_SELECT + " ORDER BY p.created_at DESC, p.id DESC", fetch="all")
    return [_project_row(r) for r in rows]


def get_project(project_id: int) -> dict | None:
    row, _ = _run(_PROJECT_SELECT + " WHERE p.id = %s", (project_id,), fetch="one")
    return _project_row(row) if row else None


def project_name_exists(name: str, exclude_id: int | None = None) -> bool:
    row, _ = _run("SELECT id FROM projects WHERE name = %s", (name,), fetch="one")
    return bool(row) and row[0] != exclude_id


def create_project(data: dict) -> dict:
    values = tuple(data.get(k) for k in _PROJECT_FIELDS) + (datetime.now(timezone.utc).isoformat(),)
    row, _ = _run(
        "INSERT INTO projects (name, description, start_date, end_date, created_at) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id", values, fetch="one")
    return get_project(row[0])


def update_project(project_id: int, changes: dict) -> dict | None:
    changes = {k: v for k, v in changes.items() if k in _PROJECT_FIELDS}
    if changes:
        sets = ", ".join(f"{k} = %s" for k in changes)
        _run(f"UPDATE projects SET {sets} WHERE id = %s", tuple(changes.values()) + (project_id,))
    return get_project(project_id)


def delete_project(project_id: int) -> bool:
    """프로젝트와 참여 명단만 삭제한다. 기업 분석 데이터·원본 PDF는 남는다."""
    _run("DELETE FROM project_companies WHERE project_id = %s", (project_id,))
    _, count = _run("DELETE FROM projects WHERE id = %s", (project_id,))
    return count > 0


def _project_member_split(project_id: int) -> tuple[list[str], list[str]]:
    """참여 기업을 (이 프로젝트에만 있는 기업, 다른 프로젝트에도 있는 기업)으로 나눈다."""
    rows, _ = _run("SELECT pc.business_no, (SELECT COUNT(*) FROM project_companies o WHERE o.business_no = pc.business_no "
                   "AND o.project_id <> pc.project_id) FROM project_companies pc WHERE pc.project_id = %s ORDER BY pc.business_no",
                   (project_id,), fetch="all")
    exclusive = [bn for bn, others in rows if not others]
    shared = [bn for bn, others in rows if others]
    return exclusive, shared


def project_purge_preview(project_id: int) -> dict:
    """전체 삭제 전에 경고창에 보여 줄 건수."""
    exclusive, shared = _project_member_split(project_id)
    # 아무것도 입력되지 않은 행(미발송·미정·메모 없음)은 기록으로 세지 않는다
    sales, _ = _run("SELECT COALESCE(SUM(CASE WHEN dm_sent OR decision IS NOT NULL OR memo IS NOT NULL THEN 1 ELSE 0 END), 0), "
                    "COALESCE(SUM(CASE WHEN dm_sent THEN 1 ELSE 0 END), 0), "
                    "COALESCE(SUM(CASE WHEN decision IS NOT NULL THEN 1 ELSE 0 END), 0), "
                    "COALESCE(SUM(CASE WHEN memo IS NOT NULL THEN 1 ELSE 0 END), 0) "
                    "FROM sales_activities WHERE project_id = %s", (project_id,), fetch="one")
    return {"companies": len(exclusive) + len(shared), "exclusive_companies": len(exclusive), "shared_companies": len(shared),
            "sales_records": int(sales[0] or 0), "dm_sent": int(sales[1] or 0), "decisions": int(sales[2] or 0), "memos": int(sales[3] or 0)}


def purge_project(project_id: int) -> dict:
    """프로젝트 전체 삭제: 이 프로젝트에만 있는 기업은 분석 정보·원본 PDF까지 완전히 삭제하고, 다른 프로젝트에도
    참여 중인 기업은 이 프로젝트 명단·영업 기록에서만 뺀다(다른 프로젝트 데이터 보호). 마지막으로 프로젝트 자체를 지운다.
    영업 기록(sales_activities)은 참여 명단 FK cascade로 함께 지워진다."""
    preview = project_purge_preview(project_id)
    exclusive, _ = _project_member_split(project_id)
    deleted = 0
    for bn in exclusive:
        if delete_company_and_pdf(bn):
            deleted += 1
    _run("DELETE FROM sales_activities WHERE project_id = %s", (project_id,))  # SQLite에서도 확실히
    delete_project(project_id)
    return {**preview, "deleted_companies": deleted}


def add_companies_to_project(project_id: int, business_nos: list[str]) -> int:
    """이미 참여 중이면 건너뛴다. 반환: 새로 추가된 수."""
    added = 0
    now = datetime.now(timezone.utc).isoformat()
    for bn in dict.fromkeys(business_nos):
        _, count = _run("INSERT INTO project_companies (project_id, business_no, added_at) VALUES (%s, %s, %s) "
                        "ON CONFLICT (project_id, business_no) DO NOTHING", (project_id, bn, now))
        added += max(count, 0)
    return added


def remove_company_from_project(project_id: int, business_no: str) -> bool:
    _, count = _run("DELETE FROM project_companies WHERE project_id = %s AND business_no = %s", (project_id, business_no))
    return count > 0


def project_names_by_company() -> dict[str, list[str]]:
    """모든 기업의 참여 프로젝트 이름 — 목록 화면용으로 쿼리 한 번에 가져온다."""
    rows, _ = _run("SELECT pc.business_no, p.name FROM project_companies pc JOIN projects p ON p.id = pc.project_id "
                   "ORDER BY p.created_at DESC", fetch="all")
    out: dict[str, list[str]] = {}
    for bn, name in rows:
        out.setdefault(bn, []).append(name)
    return out


def projects_of_company(business_no: str) -> list[dict]:
    rows, _ = _run("SELECT p.id, p.name, p.start_date, p.end_date FROM projects p JOIN project_companies pc ON pc.project_id = p.id "
                   "WHERE pc.business_no = %s ORDER BY p.created_at DESC", (business_no,), fetch="all")
    return [{"id": r[0], "name": r[1], "status": project_status(_iso(r[2]), _iso(r[3]))} for r in rows]


# ---------------------------------------------------------------------------
# 영업 관리: 프로젝트 참여 기업별 우편(DM) 발송 여부 · 승인/거절 (sales_activities)
# 같은 기업이라도 프로젝트(지원사업)마다 따로 관리한다. 행이 없으면 '미발송·미정'.
# ---------------------------------------------------------------------------
SALES_DECISIONS = ("승인", "거절")


def list_sales(project_id: int | None = None) -> list[dict]:
    """프로젝트 참여 명단 전체 + 영업 현황. project_id가 없으면 모든 프로젝트."""
    rows, _ = _run(
        "SELECT pc.project_id, p.name, pc.business_no, s.dm_sent, s.dm_sent_at, s.decision, s.decided_at, s.updated_at, "
        "s.memo, s.memo_updated_at "
        "FROM project_companies pc JOIN projects p ON p.id = pc.project_id "
        "LEFT JOIN sales_activities s ON s.project_id = pc.project_id AND s.business_no = pc.business_no"
        + (" WHERE pc.project_id = %s" if project_id else "") + " ORDER BY p.created_at DESC, pc.business_no",
        (project_id,) if project_id else (), fetch="all")
    companies = {c.business_no: c for c in list_companies(project_id)}
    out = []
    for pid, pname, bn, dm_sent, dm_sent_at, decision, decided_at, updated_at, memo, memo_updated_at in rows:
        c = companies.get(bn)
        if c is None:
            continue
        out.append({
            "project_id": pid, "project_name": pname, "business_no": bn, "company_name": c.company_name,
            "representative": c.representative, "postal_code": c.postal_code, "address": c.address,
            "industry_name": c.industry_name, "credit_grade": c.credit_grade,
            "dm_sent": bool(dm_sent), "dm_sent_at": _iso(dm_sent_at), "decision": decision,
            "decided_at": _iso(decided_at), "updated_at": _iso(updated_at),
            "memo": memo, "memo_updated_at": _iso(memo_updated_at),
        })
    return out


def is_project_member(project_id: int, business_no: str) -> bool:
    row, _ = _run("SELECT 1 FROM project_companies WHERE project_id = %s AND business_no = %s", (project_id, business_no), fetch="one")
    return bool(row)


def update_sales(project_id: int, business_no: str, changes: dict) -> dict:
    """changes: dm_sent(bool) · decision('승인'|'거절'|None) · memo(str|None) 중 바꿀 것만. 발송일·처리일·메모 수정 일시는 바뀔 때 기록."""
    row, _ = _run("SELECT dm_sent, dm_sent_at, decision, decided_at, memo, memo_updated_at FROM sales_activities "
                  "WHERE project_id = %s AND business_no = %s", (project_id, business_no), fetch="one")
    dm_sent, dm_sent_at, decision, decided_at, memo, memo_updated_at = (
        (bool(row[0]), _iso(row[1]), row[2], _iso(row[3]), row[4], _iso(row[5])) if row else (False, None, None, None, None, None))
    today = date.today().isoformat()
    if "dm_sent" in changes and bool(changes["dm_sent"]) != dm_sent:
        dm_sent = bool(changes["dm_sent"])
        dm_sent_at = today if dm_sent else None
    if "decision" in changes and changes["decision"] != decision:
        decision = changes["decision"]
        decided_at = today if decision else None
    now = datetime.now(timezone.utc).isoformat()
    if "memo" in changes:
        new_memo = (changes["memo"] or "").strip() or None  # 빈 메모는 삭제
        if new_memo != memo:
            memo, memo_updated_at = new_memo, (now if new_memo else None)
    _run("INSERT INTO sales_activities (project_id, business_no, dm_sent, dm_sent_at, decision, decided_at, updated_at, memo, memo_updated_at) "
         "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (project_id, business_no) DO UPDATE SET "
         "dm_sent = excluded.dm_sent, dm_sent_at = excluded.dm_sent_at, decision = excluded.decision, "
         "decided_at = excluded.decided_at, updated_at = excluded.updated_at, memo = excluded.memo, memo_updated_at = excluded.memo_updated_at",
         (project_id, business_no, dm_sent if _pg_url() else int(dm_sent), dm_sent_at, decision, decided_at, now, memo, memo_updated_at))
    return {"project_id": project_id, "business_no": business_no, "dm_sent": dm_sent, "dm_sent_at": dm_sent_at,
            "decision": decision, "decided_at": decided_at, "updated_at": now, "memo": memo, "memo_updated_at": memo_updated_at}


def source_pdf_path(business_no: str) -> str:
    """버킷 안 경로 규칙 `{용도}/{식별자}.{확장자}` (docs/SUPABASE_STRUCTURE.md). 한글 파일명은
    Storage 경로에 쓰지 않고 source_pdfs.filename에 따로 둔다."""
    return f"source-pdfs/{business_no}.pdf"


def save_source_pdf(business_no: str, filename: str, content: bytes) -> None:
    """원본 PDF 보관. Postgres 모드에서는 파일을 Storage 버킷에, 파일명·크기·경로는
    source_pdfs 테이블에 저장한다(서버 파일시스템이 재시작 때 지워지는 Render에서도 보존).
    SQLite 모드에서는 uploads/에 이미 있으므로 아무것도 하지 않는다."""
    if not _pg_url():
        return
    path = source_pdf_path(business_no)
    object_storage.upload(path, content)
    with _pg_conn() as conn:
        conn.execute(
            """
            INSERT INTO source_pdfs (business_no, filename, size_bytes, storage_path, uploaded_at)
            VALUES (%s, %s, %s, %s, now())
            ON CONFLICT (business_no) DO UPDATE SET
                filename = excluded.filename, size_bytes = excluded.size_bytes,
                storage_path = excluded.storage_path, uploaded_at = excluded.uploaded_at
            """,
            (business_no, filename, len(content), path),
        )


def list_source_pdfs(project_id: int | None = None) -> list[dict]:
    """업로드된 원본 PDF 목록(기업당 1개, 최신 업로드). project_id가 있으면 그 프로젝트 참여 기업만.
    반환: [{business_no, company_name, filename, size_bytes, uploaded_at}] — 최근 업로드순."""
    companies = {c.business_no: c for c in list_companies(project_id)}
    if _pg_url():
        rows, _ = _run("SELECT business_no, filename, size_bytes, uploaded_at FROM source_pdfs", fetch="all")
        items = [{"business_no": r[0], "filename": r[1], "size_bytes": r[2], "uploaded_at": _iso(r[3])}
                 for r in rows if r[0] in companies]
    else:  # SQLite 모드: 원본은 uploads/ 파일
        items = []
        for c in companies.values():
            path = Path(c.source_pdf) if c.source_pdf else None
            if path and path.exists():
                items.append({"business_no": c.business_no, "filename": path.name, "size_bytes": path.stat().st_size,
                              "uploaded_at": c.parsed_at.isoformat()})
    for item in items:
        company = companies[item["business_no"]]
        item["company_name"] = company.company_name
        item["missed"] = company.extraction_coverage.get("missed")
        item["target"] = company.extraction_coverage.get("target")
    return sorted(items, key=lambda i: i["uploaded_at"] or "", reverse=True)


def delete_company_and_pdf(business_no: str) -> bool:
    """PDF 업로드 화면의 삭제: 원본 PDF(Storage·메타데이터 또는 uploads/ 파일)와 기업 분석 정보를 함께 지우고,
    모든 프로젝트 참여 명단에서도 빠진다. 반환: 기업이 있었는지."""
    company = load_company(business_no)
    if company is None:
        return False
    if _pg_url():
        row, _ = _run("SELECT storage_path FROM source_pdfs WHERE business_no = %s", (business_no,), fetch="one")
        if row:
            object_storage.delete(row[0])
        _run("DELETE FROM source_pdfs WHERE business_no = %s", (business_no,))
    elif company.source_pdf and Path(company.source_pdf).exists():
        Path(company.source_pdf).unlink()
    return delete_company(business_no)


def load_source_pdf(company: Company) -> tuple[str, bytes] | None:
    """(파일명, 내용). 없으면 None."""
    if _pg_url():
        with _pg_conn() as conn:
            row = conn.execute(
                "SELECT filename, storage_path FROM source_pdfs WHERE business_no = %s", (company.business_no,)
            ).fetchone()
        if not row:
            return None
        content = object_storage.download(row[1])
        return (row[0], content) if content is not None else None
    if not company.source_pdf:
        return None
    path = Path(company.source_pdf)
    return (path.name, path.read_bytes()) if path.exists() else None


def list_issues(project_id: int | None = None) -> list[tuple[Company, ValidationIssue]]:
    return [(company, issue) for company in list_companies(project_id) for issue in company.issues]


def update_company(business_no: str, update: CompanyUpdate) -> Company | None:
    """검증 대기열의 "직접 수정" — 수정한 필드와 관련된 이슈는 해결된 것으로 보고 제거한다."""
    company = load_company(business_no)
    if company is None:
        return None
    changed_fields = update.model_dump(exclude_unset=True)
    for key, value in changed_fields.items():
        setattr(company, key, value)
    company.issues = [i for i in company.issues if i.field not in changed_fields]
    save_company(company)
    return company


def fiscal_year(company: Company) -> str | None:
    """요약 손익계산서의 가장 최근 결산연도(목록·검색의 '최근값' 기준 연도)."""
    years = [y for y in company.income_summary.get("매출액", {}) if y.isdigit()]
    return max(years) if years else None


def latest_value(company: Company, field: str, table: str = "income_summary") -> float | None:
    """최근 결산연도의 숫자 값. 연도는 실제 표 연도(2022~2024 기업도 있음)를 따르고,
    "흑자전환" 같은 문자 값이나 "연도미상" 열은 제외한다."""
    series = getattr(company, table).get(field, {})
    numeric = {y: v for y, v in series.items() if y.isdigit() and isinstance(v, (int, float))}
    if not numeric:
        return None
    return numeric[max(numeric)]


def latest_revenue(company: Company) -> float | None:
    return latest_value(company, "매출액")


# 목록·검색에 쓰는 최근 지표 (상세 화면 상단 KPI와 같은 값)
METRICS = {
    "revenue": lambda c: latest_value(c, "매출액"),
    "operating_profit": lambda c: latest_value(c, "영업이익"),
    "net_income": lambda c: latest_value(c, "당기순이익"),
    "debt_ratio": lambda c: latest_value(c, "부채비율", "ratio_summary"),
}


def to_list_item(company: Company) -> CompanyListItem:
    """기업목록/영업 대상 분류 화면이 공통으로 쓰는 요약 행. 두 화면이 완전히 동일한
    항목 구성을 쓰기로 해서 여기 한 곳에서만 정의한다."""
    return CompanyListItem(
        business_no=company.business_no,
        company_name=company.company_name,
        industry_name=company.industry_name,
        credit_grade=company.credit_grade,
        status=company.status,
        fiscal_year=fiscal_year(company),
        revenue_latest=METRICS["revenue"](company),
        operating_profit_latest=METRICS["operating_profit"](company),
        net_income_latest=METRICS["net_income"](company),
        debt_ratio_latest=METRICS["debt_ratio"](company),
        parsed_at=company.parsed_at,
    )


def filter_companies(
    companies: list[Company],
    *,
    q: str | None = None,
    industry: str | None = None,
    grade_band_filter: str | None = None,
    revenue_min: float | None = None,
    revenue_max: float | None = None,
    ranges: dict[str, tuple[float | None, float | None]] | None = None,
) -> list[Company]:
    """기업목록/영업 대상 분류 화면이 공통으로 쓰는 검색·필터 로직.
    ranges: {지표(METRICS 키): (최소, 최대)} — 양 끝 포함. 범위를 지정한 지표 값이 없는 기업은 제외."""
    if q:
        needle = q.strip()
        companies = [c for c in companies if needle in c.company_name or needle in c.business_no]
    if industry:
        companies = [c for c in companies if c.industry_name == industry]
    if grade_band_filter:
        companies = [c for c in companies if grade_band(c.credit_grade) == grade_band_filter]
    if revenue_min is not None:
        companies = [c for c in companies if (latest_revenue(c) or 0) >= revenue_min]
    if revenue_max is not None:
        companies = [c for c in companies if (latest_revenue(c) or 0) < revenue_max]
    for metric, (lo, hi) in (ranges or {}).items():
        if lo is None and hi is None:
            continue
        get = METRICS[metric]
        companies = [c for c in companies if get(c) is not None
                     and (lo is None or get(c) >= lo) and (hi is None or get(c) <= hi)]
    return companies


_GRADE_BASES = ("aaa", "aa", "a", "bbb", "bb", "b", "ccc", "cc", "c", "d")
_GRADE_MODIFIERS = {"+": 0, "0": 1, "": 1, "-": 2}


def _grade_rank(credit_grade: str | None) -> tuple[int, int] | None:
    """신용등급을 우량한 순서(aaa → d)로 비교하기 위한 키. 형식이 다르면 None."""
    if not credit_grade:
        return None
    g = credit_grade.lower()
    base = g.rstrip("+-0")
    if base not in _GRADE_BASES:
        return None
    return _GRADE_BASES.index(base), _GRADE_MODIFIERS.get(g[len(base):], 1)


SORT_KEYS = {
    "company_name": lambda c: c.company_name,
    "business_no": lambda c: c.business_no,
    "industry_name": lambda c: c.industry_name,
    "revenue_latest": latest_revenue,
    "operating_profit_latest": lambda c: latest_value(c, "영업이익"),
    "net_income_latest": lambda c: latest_value(c, "당기순이익"),
    "debt_ratio_latest": lambda c: latest_value(c, "부채비율", "ratio_summary"),
    "fiscal_year": fiscal_year,
    "credit_grade": lambda c: _grade_rank(c.credit_grade),
    "status": lambda c: c.status,
    "parsed_at": lambda c: c.parsed_at,
}


def sort_companies(companies: list[Company], sort: str | None, order: str = "desc") -> list[Company]:
    """기업목록/영업 대상 분류 화면의 열 정렬. 값이 없는 항목은 정렬 방향과 무관하게
    항상 맨 뒤에 둔다. 알 수 없는 sort 키는 기본 정렬(최근 등록순)로 처리한다."""
    key_fn = SORT_KEYS.get(sort or "")
    if key_fn is None:
        return sorted(companies, key=lambda c: c.parsed_at, reverse=True)
    present = [c for c in companies if key_fn(c) is not None]
    missing = [c for c in companies if key_fn(c) is None]
    present.sort(key=key_fn, reverse=(order == "desc"))
    return present + missing


# 매출액 구간(백만원, 최근 결산연도). (이름, 이상, 미만) — 상한 None은 끝없음
REVENUE_BANDS = [
    ("10억 미만", None, 1000), ("10~30억", 1000, 3000), ("30~50억", 3000, 5000),
    ("50~100억", 5000, 10000), ("100~300억", 10000, 30000), ("300억 이상", 30000, None),
]


def revenue_band_counts(companies: list[Company]) -> list[dict]:
    """매출액 구간별 기업 수. 매출 정보가 없는 기업은 마지막 '매출 정보 없음'."""
    out = [{"label": name, "min": lo, "max": hi, "count": 0} for name, lo, hi in REVENUE_BANDS]
    missing = 0
    for c in companies:
        rev = latest_revenue(c)
        if rev is None:
            missing += 1
            continue
        for band in out:
            if (band["min"] is None or rev >= band["min"]) and (band["max"] is None or rev < band["max"]):
                band["count"] += 1
                break
    out.append({"label": "매출 정보 없음", "min": None, "max": None, "count": missing})
    return out


def credit_grade_counts(companies: list[Company]) -> dict[str, int]:
    """실제 신용등급별 기업 수. 우량한 등급부터(aaa → d), 미평가는 맨 뒤."""
    counts: dict[str, int] = {}
    for c in companies:
        key = c.credit_grade.lower() if c.credit_grade else "미평가"
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: _grade_rank(kv[0]) or (99, 0)))


def grade_band(credit_grade: str | None) -> str:
    """대시보드 신용등급 분포용 구간 — 목업 도넛 범례(A~BBB/BB/B/CCC 이하)와 동일."""
    if not credit_grade:
        return "미평가"
    g = credit_grade.lower()
    if g.startswith("a") or g.startswith("bbb"):
        return "A~BBB"
    if g.startswith("bb"):
        return "BB"
    if g.startswith("b"):
        return "B"
    return "CCC 이하"
