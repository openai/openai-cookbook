FROM docker.io/cloudflare/sandbox:0.12.8
RUN apt-get update && apt-get install -y --no-install-recommends ripgrep util-linux \
    && npm install -g @openai/codex@alpha \
    && rm -rf /var/lib/apt/lists/*
