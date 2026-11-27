FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY agent/pyproject.toml agent/README.md ./agent/
COPY agent/src ./agent/src
RUN uv sync --locked --no-dev
ENV SOMNIA_HOST=0.0.0.0
CMD [".venv/bin/somnia-api"]
