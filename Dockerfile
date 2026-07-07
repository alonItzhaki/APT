FROM node:20-slim AS frontend
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable
WORKDIR /build/frontend
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.12-slim
WORKDIR /app/backend
COPY backend/pyproject.toml ./
COPY backend/apt ./apt
RUN pip install --no-cache-dir .
COPY --from=frontend /build/frontend/dist /app/frontend/dist
ENV APT_FRONTEND_DIST=/app/frontend/dist
CMD ["python", "-m", "apt.web_main"]
