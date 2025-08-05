# Optimizing OpenAI GPT-OSS Models with NVIDIA TensorRT-LLM

This notebook provides a step-by-step guide on how to optimizing `gpt-oss` models using NVIDIA's TensorRT-LLM for high-performance inference. TensorRT-LLM provides users with an easy-to-use Python API to define Large Language Models (LLMs) and support state-of-the-art optimizations to perform inference efficiently on NVIDIA GPUs. TensorRT-LLM also contains components to create Python and C++ runtimes that orchestrate the inference execution in performant way.


TensorRT-LLM supports both models:
- `gpt-oss-20b`
- `gpt-oss-120b`

In this guide, we will run `gpt-oss-20b`, if you want to try the larger model or want more customization refer to [this](https://github.com/NVIDIA/TensorRT-LLM/tree/main/docs/source/blogs/tech_blog) deployment guide.

Note: It’s important to ensure that your input prompts follow the [harmony response](http://cookbook.openai.com/articles/openai-harmony) format as the model will not function correctly otherwise, not needed in this guide.

## Prerequisites

### Hardware
To run the 20B model and the TensorRT-LLM build process, you will need an NVIDIA GPU with at least 16GB+ of VRAM.

> Recommended GPUs: NVIDIA RTX 50 Series (e.g. RTX 5090), NVIDIA H100, or L40S.

### Software
- CUDA Toolkit 12.8 or later
- Python 3.12 or later

## Installling TensorRT-LLM

There are various ways to install TensorRT-LLM, in this guide, we will using pre-built docker container from NVIDIA NGC and build it from source.

## Using NGC

Pull the pre-built TensorRT-LLM container for GPT-OSS from NVIDIA NGC.
This is the easiest way to get started and ensures all dependencies are included.

```bash
docker pull nvcr.io/nvidia/tensorrt-llm/release:gpt-oss-dev
docker run --gpus all -it --rm -v $(pwd):/workspace nvcr.io/nvidia/tensorrt-llm/release:gpt-oss-dev
```

## Using Docker (build from source)

Alternatively, you can build the TensorRT-LLM container from source.
This is useful if you want to modify the source code or use a custom branch.
See the official instructions here: https://github.com/NVIDIA/TensorRT-LLM/tree/feat/gpt-oss/docker

The following commands will install required dependencies, clone the repository,
check out the GPT-OSS feature branch, and build the Docker container:

```bash
#Update package lists and install required system packages
sudo apt-get update && sudo apt-get -y install git git-lfs build-essential cmake

# Initialize Git LFS (Large File Storage) for handling large model files
git lfs install

# Clone the TensorRT-LLM repository
git clone https://github.com/NVIDIA/TensorRT-LLM.git
cd TensorRT-LLM

# Check out the branch with GPT-OSS support
git checkout feat/gpt-oss

# Initialize and update submodules (required for build)
git submodule update --init --recursive

# Pull large files (e.g., model weights) managed by Git LFS
git lfs pull

# Build the release Docker image
make -C docker release_build

# Run the built Docker container
make -C docker release_run 
```

TensorRT-LLM will be available through pip soon

> Note on GPU Architecture: The first time you run the model, TensorRT-LLM will build an optimized engine for your specific GPU architecture (e.g., Hopper, Ada, or Blackwell). If you see warnings about your GPU's CUDA capability (e.g., sm_90, sm_120) not being compatible with the PyTorch installation, ensure you have the latest NVIDIA drivers and a matching CUDA Toolkit version for your version of PyTorch.

# Verifying TensorRT-LLM Installation

```python
from tensorrt_llm import LLM, SamplingParams
```

# Utilizing TensorRT-LLM Python API

In the next code cell, we will demonstrate how to use the TensorRT-LLM Python API to:
1. Downloads the specified model weights from Hugging Face 
2. Automatically build the TensorRT engine for your GPU architecture if it does not already exist.
3. Load the model and prepare it for inference.
4. Run a simple text generation example to verify everything is working.

**Note**: The first run may take several minutes as it downloads the model and builds the engine.
Subsequent runs will be much faster, as the engine will be cached.

```python
llm = LLM(model="openai/gpt-oss-20b")
```

```python
prompts = ["Hello, my name is", "The capital of France is"]
sampling_params = SamplingParams(temperature=0.8, top_p=0.95)
for output in llm.generate(prompts, sampling_params):
    print(f"Prompt: {output.prompt!r}, Generated text: {output.outputs[0].text!r}")
```

# Conclusion and Next Steps
Congratulations! You have successfully optimized and run a large language model using the TensorRT-LLM Python API.

In this notebook, you have learned how to:
- Set up your environment with the necessary dependencies.
- Use the `tensorrt_llm.LLM` API to download a model from the Hugging Face Hub.
- Automatically build a high-performance TensorRT engine tailored to your GPU.
- Run inference with the optimized model.


You can explore more advanced features to further improve performance and efficiency:

- Benchmarking: Try running a [benchmark](https://nvidia.github.io/TensorRT-LLM/performance/performance-tuning-guide/benchmarking-default-performance.html#benchmarking-with-trtllm-bench) to compare the latency and throughput of the TensorRT-LLM engine against the original Hugging Face model. You can do this by iterating over a larger number of prompts and measuring the execution time.

- Quantization: TensorRT-LLM [supports](https://github.com/NVIDIA/TensorRT-Model-Optimizer) various quantization techniques (like INT8 or FP8) to reduce model size and accelerate inference with minimal impact on accuracy. This is a powerful feature for deploying models on resource-constrained hardware.

- Deploy with NVIDIA Dynamo: For production environments, you can deploy your TensorRT-LLM engine using the [NVIDIA Dynamo](https://docs.nvidia.com/dynamo/latest/) for robust, scalable, and multi-model serving. 