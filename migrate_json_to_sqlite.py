"""기존 data/*.json 파일들을 새 SQLite DB(data/companies.db)로 옮긴다.

원본 JSON 파일은 건드리지 않는다 — 이관 결과를 확인한 뒤 필요하면 수동으로 정리할 것.
실행: python migrate_json_to_sqlite.py
"""
from pathlib import Path

from backend import storage
from backend.models import Company
from backend.paths import DATA_DIR, DB_PATH


def main():
    json_files = sorted(Path(DATA_DIR).glob("*.json"))
    for f in json_files:
        company = Company.model_validate_json(f.read_text(encoding="utf-8"))
        storage.save_company(company)

    print(f"{len(json_files)}개 회사를 {DB_PATH}로 이관했습니다.")
    print("원본 JSON 파일은 그대로 남아있습니다. 확인 후 필요하면 수동으로 정리하세요.")


if __name__ == "__main__":
    main()
