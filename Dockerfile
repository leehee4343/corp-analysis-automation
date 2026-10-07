FROM python:3.12-slim

# LibreOffice(impress)·나눔고딕: 영업 관리 '이미지 다운로드'에서 공문 PPTX를 PDF로 바꿀 때 쓴다(backend/letter/image.py)
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-kor \
    libreoffice-impress fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/
COPY frontend/ frontend/
# 공문 글꼴 맑은 고딕 -> 나눔고딕 대체
RUN cp backend/letter/fonts-malgun-alias.conf /etc/fonts/conf.d/30-malgun-alias.conf && fc-cache -f

EXPOSE 8000
CMD uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8000}
