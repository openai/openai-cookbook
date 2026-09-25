FROM python:3.14-slim


RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates curl file git nodejs npm poppler-utils ripgrep \
    && npm install --global @openai/codex@alpha \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /workspace /codex-home

ENV CODEX_HOME=/codex-home

WORKDIR /workspace

# Copy a local, non-sensitive sample into the sandbox workspace.
COPY sample_report.txt /workspace/sample_report.txt
