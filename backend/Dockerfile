# syntax=docker/dockerfile:1.7

# ---------- Builder stage ----------
# Installs deps into a self-contained venv at /opt/venv. pygit2 ships
# manylinux wheels that bundle libgit2 + openssl + libssh2, so no system
# libgit2 or compilers are needed.
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    VIRTUAL_ENV=/opt/venv

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src

RUN uv venv /opt/venv \
 && uv pip install --no-cache .

# ---------- Runtime stage ----------
FROM python:3.12-slim AS runtime

# Only ca-certificates is needed at runtime (for HTTPS git remotes via the
# bundled openssl inside pygit2). libgit2 itself ships inside the pygit2 wheel.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /app/src /app/src

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LIBRETA_CONTENT_DIR=/content

WORKDIR /app
EXPOSE 8080

CMD ["uvicorn", "libreta.main:app", "--host", "0.0.0.0", "--port", "8080"]
