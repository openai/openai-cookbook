FROM python:3.14-slim

WORKDIR /app
COPY examples/agents_api/sandboxes/digitalocean/environment.yaml ./examples/agents_api/sandboxes/digitalocean/environment.yaml
COPY examples/agents_api/sandboxes/digitalocean/webhook_managed/handler.py ./examples/agents_api/sandboxes/digitalocean/webhook_managed/handler.py
RUN python -m pip install --no-cache-dir uv \
    && uv pip install --system -r examples/agents_api/sandboxes/digitalocean/webhook_managed/handler.py

EXPOSE 8080
CMD ["python", "examples/agents_api/sandboxes/digitalocean/webhook_managed/handler.py"]
