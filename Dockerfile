# Runs the read-only remote MCP server (remote_main.py). For the local,
# stdio, full read+write server (main.py) run it directly via `uv run main.py`
# instead — it is not meant to be deployed as a network service.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY main.py remote_main.py ./
COPY src ./src

RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

CMD ["uv", "run", "remote_main.py"]
