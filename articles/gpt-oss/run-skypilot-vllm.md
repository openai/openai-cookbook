# How to run gpt-oss with SkyPilot and vLLM

[SkyPilot](https://skypilot.readthedocs.io/) is an open-source system that lets you run AI workloads on any infrastructure, cloud or K8s, with unified execution and high GPU availability. Combined with [vLLM](https://docs.vllm.ai/en/latest/), you can deploy **gpt-oss-20b** or **gpt-oss-120b** models across 16+ cloud providers and on-prem GPU workstations to Kubernetes clusters, with automatic failover and cost optimization.

This guide shows you how to leverage SkyPilot's multi-cloud capabilities to serve gpt-oss models at scale, building on top of the vLLM serving infrastructure covered in [our vLLM guide](https://cookbook.openai.com/articles/gpt-oss/run-vllm).

## Why SkyPilot + vLLM?

Using SkyPilot with vLLM provides several advantages:

- **Multi-cloud deployment**: Run on AWS, GCP, Azure, Lambda Labs, RunPod, and 10+ other clouds
- **On-premises and Kubernetes support**: Deploy on your own GPU workstations or existing K8s clusters
- **Reserved GPU optimization**: Efficiently utilize your pre-allocated cloud resources and reserved instances
- **Automatic GPU provisioning**: SkyPilot finds available GPUs across clouds and on-prem infrastructure
- **Cost optimization**: Automatically chooses the cheapest cloud/region or uses your existing hardware
- **Built-in autoscaling**: SkyServe provides production-ready scaling and load balancing across hybrid environments
- **Spot instance support**: Save up to 70% with automatic failover between spot, on-demand, and on-prem resources

## Prerequisites

Before starting, you'll need:

- **Python 3.11+** installed on your local machine
- **Cloud credentials** for at least one provider (AWS, GCP, Azure, Lambda Labs, Nebius, etc.)
- **GPU availability** in your chosen cloud(s)

## Quick Setup

1. **Install SkyPilot**  
   Install SkyPilot with support for all cloud providers:

```shell
pip install 'skypilot[all]'
```

2. **Configure cloud credentials**  
   SkyPilot will automatically detect credentials from your cloud CLI tools:

```shell
# Check which clouds are configured
sky check
```

3. **Create a SkyPilot configuration**  
   Create a file named `gpt-oss-vllm.sky.yaml`:

```yaml
resources:
  accelerators: {H100:1, H200:1}
  disk_size: 512 
  ports: 8000

envs:
  MODEL_NAME: openai/gpt-oss-20b

setup: |
  sudo apt-get update
  sudo apt-get install -y python3-dev build-essential
  uv venv --python 3.12 --seed
  source .venv/bin/activate
  uv pip install --pre vllm==0.10.1+gptoss \
    --extra-index-url https://wheels.vllm.ai/gpt-oss/ \
    --extra-index-url https://download.pytorch.org/whl/nightly/cu128 \
    --index-strategy unsafe-best-match
  uv pip install hf_xet openai==1.99.1
  hf download $MODEL_NAME

run: |
  source .venv/bin/activate
  vllm serve $MODEL_NAME \
    --host 0.0.0.0 \
    --port 8000 \
    --trust-remote-code \

service:
  replica_policy:
    min_replicas: 1
    max_replicas: 3
    target_qps_per_replica: 5.0
    upscale_delay_seconds: 300
    downscale_delay_seconds: 600
  readiness_probe: /v1/models
```

## Deploy to Any Cloud

### Basic deployment

Launch gpt-oss on the cheapest available GPU:

```shell
# For 20B model
sky launch -c gpt-oss gpt-oss-vllm.sky.yaml
# For 120B model 
sky launch -c gpt-oss gpt-oss-vllm.sky.yaml --env MODEL_NAME=openai/gpt-oss-120b 
```

SkyPilot will:
1. Find the cheapest cloud/region with available GPUs (defined in the `resources.accelerators` field)
2. Provision the instance
3. Install dependencies
4. Start the vLLM server
5. Expose the endpoint

### Get your endpoint

Once deployed, get the API endpoint:

```shell
ENDPOINT=$(sky status --endpoint 8000 gpt-oss)
echo "API available at: http://$ENDPOINT"
```

## Use the deployed model

The deployed model exposes the same OpenAI-compatible API as local vLLM.

Test with cURL:

```shell
curl http://$ENDPOINT/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openai/gpt-oss-20b",
    "messages": [
      {
        "role": "system",
        "content": "You are a helpful assistant."
      },
      {
        "role": "user", 
        "content": "Explain what MXFP4 quantization is."
      }
    ]
  }' | jq .
```

Test with Python:

```py
import os
from openai import OpenAI
 
ENDPOINT = os.getenv('ENDPOINT')
client = OpenAI(
    base_url=f"http://{ENDPOINT}/v1",
    api_key="EMPTY"
)
 
result = client.chat.completions.create(
    model="openai/gpt-oss-20b",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Explain what MXFP4 quantization is."}
    ]
)
 
print(result.choices[0].message.content)
```

## Production deployment with SkyServe

For production workloads, use [**SkyServe**](https://docs.skypilot.co/en/latest/serving/sky-serve.html) for automatic scaling, load balancing, and high availability:

```shell
sky serve up -n gpt-oss-service gpt-oss-vllm.sky.yaml
```

This provides:
- **Automatic scaling**: Scale replicas based on load
- **Load balancing**: Distribute requests across replicas
- **Health checks**: Automatic restart on failures
- **Rolling updates**: Zero-downtime deployments

Monitor your service:

```shell
sky serve status gpt-oss-service
```

## Integration with existing tools

The deployed endpoint is OpenAI-compatible, so it works with:
- [**LangChain**](https://www.langchain.com/): For building complex AI applications
- [**OpenAI Agents SDK**](https://openai.github.io/openai-agents-python/): For agentic workflows
- [**llm CLI tool**](https://github.com/simonw/llm): For command-line interactions
- **Any OpenAI-compatible client**: Drop-in replacement

## Cleanup

When you're done, clean up your resources:

```shell
# Fully terminate the cluster
sky down gpt-oss

# For SkyServe deployments
sky serve down gpt-oss-service

# Check all active resources
sky status
```
