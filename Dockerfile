FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py *.html .
COPY engine ./engine

ENV PORT=8080
EXPOSE 8080

CMD ["python", "mcp_server.py"]
