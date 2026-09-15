FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        fonts-noto-cjk \
        fonts-ipaexfont-gothic \
        libreoffice-impress \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py *.html ./
COPY *.pptx ./
COPY ai-usage-visualizer-extension.zip ./
COPY engine ./engine

ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn web_app:app --host 0.0.0.0 --port ${PORT:-8080}"]
