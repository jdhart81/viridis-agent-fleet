FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RADAR_PACKAGE_ROOT=/opt/viridis/regulatory-radar-agent

WORKDIR /app

COPY integrations/the402-regulatory-radar-adapter/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY integrations/the402-regulatory-radar-adapter/app.py /app/app.py
COPY regulatory-radar-agent /opt/viridis/regulatory-radar-agent

RUN addgroup --system viridis \
    && adduser --system --ingroup viridis viridis \
    && mkdir -p /state \
    && chown -R viridis:viridis /app /state /opt/viridis

USER viridis
EXPOSE 8420

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8420", "--workers", "1"]
