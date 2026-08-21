FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir .
RUN playwright install --with-deps chromium
COPY src src
ENV CAREER_RUNTIME=/data/runtime
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8765"]
