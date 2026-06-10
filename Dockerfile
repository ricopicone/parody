# Parody build environment — the one-command collaboration enabler.
# pandoc arrives via the pypandoc-binary pin (see parody/toolchain.py),
# so the image needs no separate pandoc install.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# pandoc-crossref pinned to the release built against the pinned pandoc
# (see parody/toolchain.py). TeX itself is not in this image; use a TeX-
# enabled derivative for `parody pdf` in CI.
ARG PANDOC_CROSSREF_VERSION=0.3.18.1
RUN apt-get update && apt-get install -y --no-install-recommends curl xz-utils \
    && curl -fsSL -o /tmp/pc.tar.xz \
    "https://github.com/lierdakil/pandoc-crossref/releases/download/v${PANDOC_CROSSREF_VERSION}/pandoc-crossref-Linux-X64.tar.xz" \
    && tar -xJf /tmp/pc.tar.xz -C /usr/local/bin pandoc-crossref \
    && rm /tmp/pc.tar.xz && apt-get purge -y curl xz-utils && rm -rf /var/lib/apt/lists/*

WORKDIR /work
COPY pyproject.toml uv.lock* README.md ./
COPY parody ./parody
RUN uv sync --frozen --no-dev || uv sync --no-dev

ENV PATH="/work/.venv/bin:$PATH"
ENTRYPOINT ["parody"]
