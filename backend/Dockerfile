# build stage
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

# grab uv from the official image (fast, no pip bootstrap needed)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# copy lockfile + manifest first so docker caches the deps layer
COPY pyproject.toml uv.lock ./

# install deps from the frozen lockfile into a venv (reproducible builds)
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
RUN uv sync --frozen --no-dev --no-install-project

# now copy the source and install the project itself
COPY . .
RUN uv sync --frozen --no-dev

# runtime stage
FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app /app

ENV PATH="/opt/venv/bin:$PATH"

EXPOSE 8000

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
