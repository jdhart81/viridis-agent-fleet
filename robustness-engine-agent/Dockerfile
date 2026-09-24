FROM python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ROBUSTNESS_ENGINE_BUNDLE_ROOT=/app/vendor

WORKDIR /app

COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

COPY src ./src
COPY adapters ./adapters
COPY vendor ./vendor
COPY schemas ./schemas
COPY RELEASE_MANIFEST.json ./RELEASE_MANIFEST.json
COPY SERVICE_SOURCE_MANIFEST.json ./SERVICE_SOURCE_MANIFEST.json
COPY ROLLBACK_PLAN.md ./ROLLBACK_PLAN.md

RUN useradd --create-home --uid 10001 robustness
USER robustness

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3)"

CMD ["uvicorn", "adapters.fastapi_server:app", "--host", "0.0.0.0", "--port", "8080"]
