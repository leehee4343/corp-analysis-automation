"""데이터 저장 경로.

로컬 개발(APP_STORAGE_ROOT 미설정)에서는 기존처럼 프로젝트 루트 기준 상대경로를
그대로 쓴다. Render 등 클라우드에 배포할 때는 영구 디스크가 마운트된 경로를
APP_STORAGE_ROOT로 지정하면 그 아래에 data/uploads/outputs를 둬서, 재배포·재시작
후에도 업로드한 PDF와 분석 결과가 사라지지 않게 한다.
"""
from __future__ import annotations

import os
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_STORAGE_ROOT = Path(os.environ["APP_STORAGE_ROOT"]) if os.environ.get("APP_STORAGE_ROOT") else _PROJECT_ROOT

DATA_DIR = _STORAGE_ROOT / "data"
UPLOADS_DIR = _STORAGE_ROOT / "uploads"
OUTPUT_DIR = _STORAGE_ROOT / "outputs"
