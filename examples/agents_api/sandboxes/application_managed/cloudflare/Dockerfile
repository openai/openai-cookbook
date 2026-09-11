FROM docker.io/cloudflare/sandbox:0.12.9
RUN apt-get update && apt-get install -y --no-install-recommends util-linux \
    && npm install -g @openai/codex@alpha \
    && mkdir -p /workspace \
    && rm -rf /var/lib/apt/lists/*
