FROM python:3.12-slim

# pygit2 needs libgit2 + build tools for the wheel build path on slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends libgit2-dev build-essential \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src

RUN uv pip install --system --no-cache .

ENV LIBRETA_CONTENT_DIR=/content
EXPOSE 8080

CMD ["uvicorn", "libreta.main:app", "--host", "0.0.0.0", "--port", "8080"]
