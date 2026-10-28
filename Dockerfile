FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=3000 \
    DATABASE_PATH=/data/lightpost.sqlite

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home --shell /usr/sbin/nologin lightpost \
    && mkdir /data \
    && chown lightpost:lightpost /data

COPY lightpost ./lightpost
COPY web ./web
COPY public ./public

USER lightpost
EXPOSE 3000
CMD ["python", "-m", "lightpost"]
