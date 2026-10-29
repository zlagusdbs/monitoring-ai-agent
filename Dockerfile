FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY policy.py net.py ./
COPY collector/ ./collector/

CMD ["python", "-m", "collector.main"]
