FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TESSERACT_LANG=spa+eng ALTIVIA_COOKIE_SECURE=1 ALTIVIA_DATA_DIR=/var/data PORT=10000
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng poppler-utils ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements-ocr.txt ./
RUN pip install --no-cache-dir -r requirements-ocr.txt
COPY altivia/ ./altivia/
COPY static/ ./static/
COPY cloud_start.py ./cloud_start.py
RUN useradd --create-home --uid 10001 appuser && mkdir -p /var/data && chown -R appuser:appuser /var/data /app
USER appuser
EXPOSE 10000
CMD ["python", "cloud_start.py"]
