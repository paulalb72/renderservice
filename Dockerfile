# Basisimage bringt Chromium + passende Systembibliotheken bereits mit
FROM mcr.microsoft.com/playwright/python:v1.56.0-jammy

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Templates muessen mitkopiert werden, weil app.py sie beim Start einliest.
COPY *.html ./
COPY app.py .

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).read()"

CMD ["gunicorn", "-b", "0.0.0.0:8000", "-w", "2", "-t", "120", "app:app"]
