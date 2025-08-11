# Verifying gpt-oss implementations

The [OpenAI gpt-oss models](https://openai.com/open-models) are introducing a lot of new concepts to the open-model ecosystem and [getting them to perform as expected might take some time](https://x.com/ClementDelangue/status/1953119901649891367). This guide is meant to help developers building inference solutions to verify their implementations or for developers who want to test any provider’s implementation on their own to gain confidence.

## Why is implementing gpt-oss models different?

The new models behave more similarly to some of our other OpenAI models than to existing open models. A couple of examples include:

1. **The harmony response format.** These models were trained on our [OpenAI harmony format](https://cookbook.openai.com/articles/openai-harmony) to structure a conversation. While regular API developers won’t need to deal with harmony in most cases, the inference providers that provide a Chat Completions-compatible, Responses-compatible or other inference API need to map the inputs correctly to the OpenAI harmony format. If the model does not receive the prompts in the right format this can have cascading generation issues and at minimum a worse function calling performance.
2. **Handling chain of thought (CoT) between tool calls**. These models can perform tool calls as part of the CoT. A consequence of this is that the model needs to receive the CoT in subsequent sampling until it reaches a final response. This means that while the raw CoT should not be displayed to end-users, it should be returned by APIs so that developers can pass it back in along with the tool call and tool output. [You can learn more about it in this separate guide](https://cookbook.openai.com/articles/gpt-oss/handle-raw-cot).
3. **Differences in actual inference code**. We published our mixture-of-experts (MoE) weights exclusively in MXFP4 format. This is still a relatively new format and along with other architecture decisions, existing inference code that was written for other open-models will have to be adapted for gpt-oss models. For that reason we published both a basic (unoptimized) [PyTorch implementation](https://github.com/openai/gpt-oss/tree/main/gpt_oss/torch), and a [more optimized Triton implementation](https://github.com/openai/gpt-oss/tree/main/gpt_oss/triton). Additionally, we verified the [vLLM implementation](https://github.com/vllm-project/vllm/blob/7e3a8dc90670fd312ce1e0d4eba9bf11c571e3ad/vllm/model_executor/models/gpt_oss.py) for correctness. We hope these can serve as educational material for other implementations.

## API Design

### Responses API

For best performance we recommend inference providers to implement our Responses API format as the API shape was specifically designed for behaviors like outputting raw CoT along with summarized CoTs (to display to users) and tool calls without bolting additional properties onto a format. The most important  
part for accurate performance is to return the raw CoT as part of the `output`.

For this we added a new `content` array to the Responses API’s `reasoning` items. The raw CoT should be wrapped into `reasoning_text` type element, making the overall output item look the following:

```
{
  "type": "reasoning",
  "id": "item_67ccd2bf17f0819081ff3bb2cf6508e60bb6a6b452d3795b",
  "status": "completed",
  "summary": [
    /* optional summary elements */
  ],
  "content": [
    {
      "type": "reasoning_text",
      "text": "The user needs to know the weather, I will call the get_weather tool."
    }
  ]
}
```

These items should be received in subsequent turns and then inserted back into the harmony formatted prompt as outlined in the [raw CoT handling guide](https://cookbook.openai.com/articles/gpt-oss/handle-raw-cot).

[Check out the Responses API docs for the whole specification](https://platform.openai.com/docs/api-reference/responses/create).

### Chat Completions

A lot of providers are offering a Chat Completions-compatible API. While we have not augmented our published API reference on the docs to provide a way to receive raw CoT, it’s still important that providers that offer the gpt-oss models via a Chat Completions-compatible API return the CoT as part of their messages and for developers to have a way to pass them back.

There is currently no generally agreed upon specification in the community with the general properties on a message being either `reasoning` or `reasoning_content`. **To be compatible with clients like the OpenAI Agents SDK we recommend using a `reasoning` field as the primary property for the raw CoT in Chat Completions**.

## Quick verification of tool calling and API shapes

To verify if a provider is working you can use the Node.js script published in our [gpt-oss GitHub repository](https://github.com/openai/gpt-oss) that you can also use to run other evals. You’ll need [Node.js](http://nodejs.org/) or a similar runtime installed to run the tests.

These tests will run a series of tool/function calling based requests to the Responses API or Chat Completions API you are trying to test. Afterwards they will evaluate both whether the right tool was called and whether the API shapes are correct.

This largely acts as a smoke test but should be a good indicator on whether the APIs are compatible with our SDKs and can handle basic function calling. It does not guarantee full accuracy of the inference implementation (see the evals section below for details on that) nor does it guarantee full compatibility with the OpenAI APIs. They should still be a helpful indicator of major implementation issues.

To run the test suite run the following commands:

```shell
# clone the repository
git clone https://github.com/openai/gpt-oss.git

# go into the compatibility test directory
cd gpt-oss/compatibility-test/

# install the dependencies
npm install

# change the provider config in providers.ts to add your provider

# run the tests
npm start -- --provider <your-provider-name>
```

Afterwards you should receive a result of both the API implementation and any details on the function call performance.

If your tests are successful, the output should show 0 invalid requests and over 90% on both pass@k and pass^k. This means the implementation should likely be correct. To be fully sure, you should also inspect the evals as described below.

If you want a detailed view of the individual responses, you can the `jsonl` file that was created in your directory.

You can also enable debug mode to view any of the actual request payloads using `DEBUG=openai-agents:openai npm start -- --provider <provider-name>` but it might get noisy. To run only one test use the `-n 1` flag for easier debugging. For testing streaming events you can use `--streaming`.

## Verifying correctness through evals

The team at Artificial Analysis is running AIME and GPQA evals for a variety of providers. If you are unsure about your provider, [check out Artificial Analysis for the most recent metrics](https://artificialanalysis.ai/models/gpt-oss-120b/providers#evaluations).

To be on the safe side you should consider running evals yourself. To run your own evals, you can find in the same repository as the test above a `gpt_oss/evals` folder that contains the test harnesses that we used to verify the AIME (16 attempts per problem), GPQA (8 attempts per problem) and Healthbench (1 attempt per problem) evals for the vLLM implementation and some of our own reference implementations. You can use the same script to test your implementations.

To test a Responses API compatible API run:

```bash
python -m gpt_oss.evals --base-url http://localhost:8000/v1 --eval aime25 --sampler responses --model openai/gpt-oss-120b --reasoning-effort high
```

To test a Chat Completions API compatible API run:

```bash
python -m gpt_oss.evals --base-url http://localhost:8000/v1 --eval aime25 --sampler chat_completions --model openai/gpt-oss-120b --reasoning-effort high
```

If you are getting similar benchmark results as those published by us and your function calling tests above succeeded you likely have a correct implementation of gpt-oss.
