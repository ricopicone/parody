# Parody build environment — the one-command collaboration enabler.
# pandoc arrives via the pypandoc-binary pin (see parody/toolchain.py),
# so the image needs no separate pandoc install.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /work
COPY pyproject.toml uv.lock* README.md ./
COPY parody ./parody
RUN uv sync --frozen --no-dev || uv sync --no-dev

ENV PATH="/work/.venv/bin:$PATH"
ENTRYPOINT ["parody"]
