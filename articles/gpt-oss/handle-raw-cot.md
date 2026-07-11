# How to handle the raw chain of thought in gpt-oss

The [gpt-oss models](https://openai.com/open-models) provide access to a raw chain of thought (CoT) meant for analysis and safety research by model implementors, but it’s also crucial for the performance of tool calling, as tool calls can be performed as part of the CoT. At the same time, the raw CoT might contain potentially harmful content or could reveal information to users that the person implementing the model might not intend (like rules specified in the instructions given to the model). You therefore should not show raw CoT to end users.

## Harmony / chat template handling

The model encodes its raw CoT as part of our [harmony response format](https://cookbook.openai.com/articles/openai-harmony). If you are authoring your own chat templates or are handling tokens directly, make sure to [check out harmony guide first](https://cookbook.openai.com/articles/openai-harmony).

To summarize a couple of things:

1. CoT will be issued to the `analysis` channel
2. After a message to the `final` channel in a subsequent sampling turn all `analysis` messages should be dropped. Function calls to the `commentary` channel can remain
3. If the last message by the assistant was a tool call of any type, the analysis messages until the previous `final` message should be preserved on subsequent sampling until a `final` message gets issued

## Chat Completions API

If you are implementing a Chat Completions API, there is no official spec for handling chain of thought in the published OpenAI specs, as our hosted models will not offer this feature for the time being. We ask you to follow [the following convention from OpenRouter instead](https://openrouter.ai/docs/use-cases/reasoning-tokens). Including:

1. Raw CoT will be returned as part of the response unless `reasoning: { exclude: true }` is specified as part of the request. [See details here](https://openrouter.ai/docs/use-cases/reasoning-tokens#legacy-parameters)
2. The raw CoT is exposed as a `reasoning` property on the message in the output
3. For delta events the delta has a `reasoning` property
4. On subsequent turns you should be able to receive the previous reasoning (as `reasoning`) and handle it in accordance with the behavior specified in the chat template section above.

When in doubt, please follow the convention / behavior of the OpenRouter implementation.

## Responses API

For the Responses API we augmented our Responses API spec to cover this case. Below are the changes to the spec as type definitions. At a high level we are:

1. Introducing a new `content` property on `reasoning`. This allows a reasoning `summary` that could be displayed to the end user to be returned at the same time as the raw CoT (which should not be shown to the end user, but which might be helpful for interpretability research).
2. Introducing a new content type called `reasoning_text`
3. Introducing two new events `response.reasoning_text.delta` to stream the deltas of the raw CoT and `response.reasoning_text.done` to indicate a turn of CoT to be completed
4. On subsequent turns you should be able to receive the previous reasoning and handle it in accordance with the behavior specified in the chat template section above.

**Item type changes**

```typescript
type ReasoningItem = {
  id: string;
  type: "reasoning";
  summary: SummaryContent[];
  // new
  content: ReasoningTextContent[];
};

type ReasoningTextContent = {
  type: "reasoning_text";
  text: string;
};

type ReasoningTextDeltaEvent = {
  type: "response.reasoning_text.delta";
  sequence_number: number;
  item_id: string;
  output_index: number;
  content_index: number;
  delta: string;
};

type ReasoningTextDoneEvent = {
  type: "response.reasoning_text.done";
  sequence_number: number;
  item_id: string;
  output_index: number;
  content_index: number;
  text: string;
};
```

**Event changes**

```typescript
...
{
	type: "response.content_part.added"
	...
}
{
	type: "response.reasoning_text.delta",
	sequence_number: 14,
	item_id: "rs_67f47a642e788191aec9b5c1a35ab3c3016f2c95937d6e91",
	output_index: 0,
	content_index: 0,
	delta: "The "
}
...
{
	type: "response.reasoning_text.done",
	sequence_number: 18,
	item_id: "rs_67f47a642e788191aec9b5c1a35ab3c3016f2c95937d6e91",
	output_index: 0,
	content_index: 0,
	text: "The user asked me to think"
}
```

**Example responses output**

```typescript
"output": [
  {
    "type": "reasoning",
    "id": "rs_67f47a642e788191aec9b5c1a35ab3c3016f2c95937d6e91",
    "summary": [
      {
        "type": "summary_text",
        "text": "**Calculating volume of gold for Pluto layer**\n\nStarting with the approximation..."
      }
    ],
    "content": [
      {
        "type": "reasoning_text",
        "text": "The user asked me to think..."
      }
    ]
  }
]

```

## Displaying raw CoT to end-users

If you are providing a chat interface to users, you should not show the raw CoT because it might contain potentially harmful content or other information that you might not intend to show to users (like, for example, instructions in the developer message). Instead, we recommend showing a summarized CoT, similar to our production implementations in the API or ChatGPT, where a summarizer model reviews and blocks harmful content from being shown.
