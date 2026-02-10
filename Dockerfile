FROM python:3.14-rc-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

COPY pyproject.toml README.md /app/
RUN uv sync --no-dev

COPY . /app
RUN mkdir -p /app/data

EXPOSE 8000
CMD ["uv", "run", "gunicorn", "-b", "0.0.0.0:8000", "app:app"]
