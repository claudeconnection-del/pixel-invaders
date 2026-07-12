# Pixel Invaders Arcade backend — build from the repo root:
#   docker build -f server/Dockerfile -t pixel-invaders-arcade .
FROM python:3.13-slim

WORKDIR /app

COPY server/requirements.txt ./server/requirements.txt
RUN pip install --no-cache-dir -r server/requirements.txt

COPY server ./server

RUN useradd --create-home arcade \
    && mkdir -p /data \
    && chown arcade:arcade /data
USER arcade

ENV ARCADE_DB_PATH=/data/arcade.db
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"

CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
