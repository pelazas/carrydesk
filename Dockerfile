# MCP server image.
#
# Runs the stdio MCP server, which is what registry indexers (Glama and others)
# start to introspect the tool list. It talks to the hosted API at
# CARRYDESK_API_BASE, so the container needs no secrets and no wallet: the three
# free tools work immediately, and the paid ones report their price rather than
# failing when CARRYDESK_PRIVATE_KEY is unset.
#
#   docker build -t carrydesk-mcp .
#   docker run --rm -i carrydesk-mcp
#
# To let the container pay for the metered tools, pass a funded hot key:
#   docker run --rm -i -e CARRYDESK_PRIVATE_KEY=0x... carrydesk-mcp
FROM python:3.12-slim

# uv gives fast, reproducible installs from the same pyproject the repo uses.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Dependency layer first so code edits don't reinstall the world.
COPY pyproject.toml README.md ./
COPY carrydesk ./carrydesk
RUN uv pip install --system --no-cache .

# Default to the hosted service. Override to point at a local instance.
ENV CARRYDESK_API_BASE=https://carry.pelazas.com \
    PYTHONUNBUFFERED=1

# Non-root: this process only makes outbound HTTPS calls and signs payment
# authorizations, so it has no reason to run privileged.
RUN useradd --create-home --uid 10001 mcp
USER mcp

# stdio transport — the indexer speaks MCP over stdin/stdout.
ENTRYPOINT ["carrydesk-mcp"]
