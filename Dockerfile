# Docker image to build the static docs pages

FROM node:22.15.0-bookworm-slim AS node

# Compilers and the Tree-sitter CLI stay in the parser stage.
FROM python:3.12.10-slim-bookworm AS parser

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules

RUN node /usr/local/lib/node_modules/npm/bin/npm-cli.js install --global tree-sitter-cli@0.25.10 --no-audit --no-fund

COPY tools/api_docs/vendor/tree-sitter-angelscript /parser
COPY tools/api_docs/src/kagdocs/patch_grammar.py /patch_grammar.py

# Patch a copy of the grammar, regenerate the C parser, and wheel it.
# The vendored upstream files in the repo stay unmodified.
RUN python /patch_grammar.py /parser/grammar.js \
    && cd /parser \
    && tree-sitter generate \
    && pip install --no-cache-dir setuptools==80.9.0 wheel==0.45.1 \
    && pip wheel --no-deps --no-build-isolation /parser -w /wheels


FROM python:3.12.10-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.6.12 /uv /uvx /bin/

COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm

WORKDIR /app

# Deps here so a generator-only change does not reinstall them.
COPY tools/api_docs/pyproject.toml tools/api_docs/uv.lock tools/api_docs/
RUN uv sync --frozen --no-dev --no-install-project --directory tools/api_docs

COPY --from=parser /wheels /wheels

COPY tools/api_docs/package.json tools/api_docs/package-lock.json tools/api_docs/
RUN cd tools/api_docs && npm ci --no-audit --no-fund

COPY tools/api_docs tools/api_docs
COPY docs docs
COPY favicon.ico favicon.ico

# The parser wheel is built in this image and is not a lockfile dependency
# Install it after sync because it would otherwise remove packages it does not know
RUN uv sync --frozen --no-dev --directory tools/api_docs \
    && uv pip install --python tools/api_docs/.venv/bin/python --no-deps /wheels/*.whl \
    && rm -rf /wheels

ENV PATH="/app/tools/api_docs/.venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

CMD ["kagdocs", "build", "--kag-dir", "/kag", "--output", "/output"]
