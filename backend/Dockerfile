FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Europe/Istanbul

WORKDIR /app

# v0.9.4: tzdata (Europe/Istanbul için ZoneInfo desteği) + TZ env
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl \
    fonts-dejavu-core \
    tzdata \
    && ln -fs /usr/share/zoneinfo/Europe/Istanbul /etc/localtime \
    && dpkg-reconfigure -f noninteractive tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY app ./app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -fsS http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
