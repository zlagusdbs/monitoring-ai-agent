FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY policy.py .
COPY collector/ ./collector/

# 수집 DB 는 호스트와 공유한다 — 에이전트가 호스트에서 읽어야 하기 때문.
CMD ["python", "-m", "collector.main"]
