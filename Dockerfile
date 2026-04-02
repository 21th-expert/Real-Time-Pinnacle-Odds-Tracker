FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

# Logs directory (mount a volume here for persistence)
RUN mkdir -p /app/logs

ENV PYTHONUNBUFFERED=1

CMD ["python", "src/poller.py"]
