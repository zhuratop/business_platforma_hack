# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
COPY scripts/templates/ /build/scripts/templates/
RUN npm run build

FROM python:3.11-slim-bookworm AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    SPR_RUNTIME=/app/runtime \
    SPR_DATA_ROOT=/input
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
RUN groupadd --gid 10001 spr \
    && useradd --uid 10001 --gid spr --no-create-home --home-dir /app spr \
    && mkdir -p /app/runtime /input/data \
    && chown spr:spr /app/runtime
COPY backend/ ./backend/
COPY scripts/ ./scripts/
COPY --from=frontend-build /build/frontend/dist/ ./frontend/dist/
USER spr
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.app.api:app", "--host", "0.0.0.0", "--port", "8000"]
