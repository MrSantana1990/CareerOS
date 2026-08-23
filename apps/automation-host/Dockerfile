FROM python:3.12-slim-bookworm
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .
RUN playwright install --with-deps chromium
RUN apt-get update && apt-get install -y --no-install-recommends xvfb && rm -rf /var/lib/apt/lists/*
COPY src src
ENV CAREER_RUNTIME=/data/runtime
CMD Xvfb :99 -screen 0 1440x900x24 -nolisten tcp & sleep 1 && DISPLAY=:99 exec uvicorn src.main:app --host 0.0.0.0 --port 8765
