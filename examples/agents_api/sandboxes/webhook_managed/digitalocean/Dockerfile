FROM python:3.14-slim

WORKDIR /app
COPY examples/agents_api/sandboxes/webhook_managed/digitalocean/handler.py ./examples/agents_api/sandboxes/webhook_managed/digitalocean/handler.py
RUN python -m pip install --no-cache-dir uv \
    && uv pip install --system -r examples/agents_api/sandboxes/webhook_managed/digitalocean/handler.py

EXPOSE 8080
CMD ["python", "examples/agents_api/sandboxes/webhook_managed/digitalocean/handler.py"]
