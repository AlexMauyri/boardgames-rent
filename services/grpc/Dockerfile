# syntax=docker/dockerfile:1

# ============================================================
# UV: база для установки зависимостей
# ============================================================
FROM python:3.14.7-slim-bookworm AS uv

COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

COPY pyproject.toml uv.lock ./

# ============================================================
# Builder: production-зависимости
# ============================================================
FROM uv AS builder-runtime

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# ============================================================
# Runtime
# ============================================================
FROM python:3.14.7-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

RUN useradd --uid 1000 app && \
    find / -xdev -perm /6000 -type f -exec chmod a-s {} + || true

WORKDIR /app

COPY --from=builder-runtime /app/.venv /app/.venv
COPY --chown=app:app app ./app

USER app

EXPOSE 50051

CMD ["python", "-m", "app.main"]

# ============================================================
# Builder: все зависимости (включая dev — для тестов)
# ============================================================
FROM uv AS builder-test

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

# ============================================================
# Test
# ============================================================
FROM python:3.14.7-slim-bookworm AS test

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

RUN useradd --uid 1000 app && \
    find / -xdev -perm /6000 -type f -exec chmod a-s {} + || true

WORKDIR /app

COPY --from=builder-test /app/.venv /app/.venv
COPY --chown=app:app app ./app
COPY --chown=app:app tests ./tests
COPY --chown=app:app pyproject.toml ./

USER app

ENTRYPOINT ["python", "-m", "pytest"]
CMD ["-v"]