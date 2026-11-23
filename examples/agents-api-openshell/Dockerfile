FROM node:24-bookworm-slim

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates curl git \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global @openai/codex@0.173.0-alpha.4 \
    && install -d /opt/codex/bin \
    && install -m 0755 "$(find /usr/local/lib/node_modules/@openai/codex -type f -path '*/bin/codex' -print -quit)" /opt/codex/bin/codex \
    && npm uninstall --global @openai/codex \
    && install -d -o 1000 -g 1000 /workspace /workspace/outputs /workspace/.codex /workspace/.tmp

COPY entrypoint.sh /opt/codex/bin/start-executor
RUN chmod 0755 /opt/codex/bin/start-executor
ENV PATH="/opt/codex/bin:${PATH}" \
    HOME=/workspace \
    TMPDIR=/workspace/.tmp \
    CODEX_HOME=/workspace/.codex
WORKDIR /workspace
USER 1000:1000
ENTRYPOINT ["/opt/codex/bin/start-executor"]
