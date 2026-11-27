FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/opt/aevra UV_LINK_MODE=copy
WORKDIR /opt/aevra
RUN pip install --no-cache-dir uv==0.9.13
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY apps ./apps
COPY src ./src
COPY configs ./configs
# Compose runs the container as the owner's uid, so every file must be world-readable.
RUN chmod -R a+rX /opt/aevra && useradd --system --uid 10001 --no-create-home aevra
USER 10001
EXPOSE 7090
CMD [".venv/bin/python", "-m", "apps.cli.main", "serve", "--port", "7090"]
