FROM python:3.14-slim

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates git nodejs npm ripgrep \
    && npm install --global @openai/codex@alpha \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir 'boto3>=1.43.34' 'flask>=3.1'

ENV CODEX_HOME=/codex-home
RUN mkdir -p /workspace /codex-home
WORKDIR /workspace

# Start Codex from the run hook, once the session is known.
COPY sandbox_server.py /opt/sandbox_server.py
EXPOSE 8080
CMD ["python", "/opt/sandbox_server.py"]
