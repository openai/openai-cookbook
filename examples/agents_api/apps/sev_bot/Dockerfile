FROM python:3.14-slim

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates git nodejs npm ripgrep \
    && npm install --global @openai/codex@alpha \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /workspace /codex-home
ENV CODEX_HOME=/codex-home
WORKDIR /workspace

RUN npx --yes skills add aws/agent-toolkit-for-aws/skills \
    --agent codex --copy --yes
