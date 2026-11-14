FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY hoito hoito
COPY ui ui
COPY server.py .
COPY recordings recordings
ENV PORT=8000
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT}"]
