"""Tesseract-OCR 한국어 언어 데이터를 프로젝트 로컬 .tessdata/ 에 내려받는다.

관리자 권한 없이 설치하면 Tesseract-OCR 설치 폴더(C:\\Program Files\\Tesseract-OCR\\tessdata)에
쓰기 권한이 없어 새 언어(kor)를 추가할 수 없다. 대신 프로젝트 로컬 폴더에 두고
backend/parser/grade_ocr.py 가 TESSDATA_PREFIX로 이 폴더를 가리키게 한다.

사용법: python setup_tessdata.py  (Tesseract-OCR 엔진 자체는 winget/공식 설치 프로그램으로 먼저 설치)
"""
import urllib.request
from pathlib import Path

TESSDATA_URL = "https://github.com/tesseract-ocr/tessdata/raw/main/{lang}.traineddata"
LANGS = ["eng", "kor"]
DEST = Path(__file__).parent / ".tessdata"


def main() -> None:
    DEST.mkdir(exist_ok=True)
    for lang in LANGS:
        target = DEST / f"{lang}.traineddata"
        if target.exists():
            print(f"skip (이미 존재): {target}")
            continue
        url = TESSDATA_URL.format(lang=lang)
        print(f"downloading {url} -> {target}")
        urllib.request.urlretrieve(url, target)
    print("완료:", DEST)


if __name__ == "__main__":
    main()
