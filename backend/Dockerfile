FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY migrate.py ./migrate.py
RUN mkdir -p /srv/data/videos && useradd -u 10001 -m kisa && chown -R kisa:kisa /srv
USER kisa
EXPOSE 8000
CMD ["sh", "-c", "python migrate.py && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips 127.0.0.1"]
