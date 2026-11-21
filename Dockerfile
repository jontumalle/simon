FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    SIMON_STORE_BACKEND=firestore

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY simon /app/simon
COPY agents /app/agents
COPY data /app/data
COPY examples /app/examples

EXPOSE 8080

CMD ["python3", "-m", "simon", "serve", "--host", "0.0.0.0"]
