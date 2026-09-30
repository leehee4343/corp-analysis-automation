"""로컬 SQLite(data/companies.db)와 uploads/의 원본 PDF를 Supabase Postgres(DATABASE_URL)로 옮긴다.

원본 SQLite·PDF 파일은 건드리지 않는다 — 이관 결과를 확인한 뒤 필요하면 수동으로 정리할 것.
같은 사업자번호가 이미 있으면 덮어쓴다(UPSERT)라 여러 번 실행해도 안전하다.
실행: DATABASE_URL=... python migrate_sqlite_to_postgres.py  (프로그램 시작.command 사용 시 .env에서 읽음)
"""
import os
import sqlite3
from pathlib import Path

from backend import storage
from backend.models import Company
from backend.paths import DB_PATH, UPLOADS_DIR


def main():
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("DATABASE_URL 환경변수가 없습니다. .env의 DATABASE_URL을 지정해 실행하세요.")

    conn = sqlite3.connect(DB_PATH)
    companies = [Company.model_validate_json(row[0]) for row in conn.execute("SELECT data FROM companies")]
    conn.close()

    pdf_count, missing = 0, []
    for company in companies:
        storage.save_company(company)
        pdf = Path(company.source_pdf) if company.source_pdf else None
        if pdf is None or not pdf.exists():
            pdf = UPLOADS_DIR / Path(company.source_pdf or "").name
        if pdf.is_file():
            storage.save_source_pdf(company.business_no, pdf.name, pdf.read_bytes())
            pdf_count += 1
        else:
            missing.append(company.company_name)

    print(f"기업 {len(companies)}개, 원본 PDF {pdf_count}개를 옮겼습니다.")
    if missing:
        print("원본 PDF를 찾지 못한 기업:", ", ".join(missing))
    print(f"Supabase 확인: {len(storage.list_companies())}개 기업. 원본 {DB_PATH}는 그대로 남아 있습니다.")


if __name__ == "__main__":
    main()
