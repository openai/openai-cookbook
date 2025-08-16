# How to work with large language models

## How large language models work

[Large language models][Large language models Blog Post] are mathematical functions that take a sequence of words (or tokens) as input and produce a sequence of words (or tokens) as output. They are trained on vast amounts of text data to learn the statistical relationships between words, allowing them to generate coherent and contextually relevant text.

These models can perform a wide range of tasks, including but not limited to:
- text generation
- summarization
- translation
- sentiment analysis
- text classification
- text completion
- text extraction
- question answering
- code generation
- code completion
- code explanation
- code debugging
- and more.

To do this, they are trained on large datasets containing diverse text from books, articles, websites, and other sources. The training process involves adjusting the model's parameters to minimize the difference between its predicted output and the actual output in the training data. This allows the model to learn patterns, grammar, facts, and even some reasoning abilities from the data it has seen. 

One such language model is the Generative Pre-trained Transformer (GPT). GPT-4o and GPT-5 power [many software products][OpenAI Customer Stories], including [GitHub Copilot] and [Replit]. These models are designed to understand and generate human-like text, making them suitable for a wide range of applications.

## How to control a large language model

Large language models can be prompted to produce output in a few ways:

- **Instruction**: Tell the model what you want
- **Completion**: Make the model finish what you want
- **Scenario**: Give the model a situation to play out
- **Demonstration**: Show the model what you want, with either:
  - A few examples (few-shot learning)
  - Thousands to millions of examples (fine-tuning)

An example of each is shown below.

### Instruction prompts

Write your instruction at the top of the prompt (or at the bottom, or both), and the model will do its best to follow the instruction and then stop. Instructions can be detailed, so don't be afraid to write a paragraph explicitly detailing the output you want, but just be aware of how many [tokens](https://help.openai.com/en/articles/4936856-what-are-tokens-and-how-to-count-them) the model can process.

Example instruction prompt:

```text
Extract the name of the author from the quotation below.

“Some humans theorize that intelligent species go extinct before they can expand into outer space. If they're correct, then the hush of the night sky is the silence of the graveyard.”
― Ted Chiang, Exhalation
```

Output:

```text
Ted Chiang
```

### Completion prompt example

Completion-style prompts take advantage of how large language models try to write text they think is most likely to come next. To steer the model, begin a pattern or sentence you want to see completed. This mode of steering large language models can take more care and experimentation. Additionally, the models won't necessarily know where to stop, so you will often need stop sequences or post-processing to cut off text generated beyond the desired output.

Example completion prompt:

```text
“Some humans theorize that intelligent species go extinct before they can expand into outer space. If they're correct, then the hush of the night sky is the silence of the graveyard.”
― Ted Chiang, Exhalation

The author of this quote is
```

Output:

```text
 Ted Chiang
```

### Scenario prompt example

Giving the model a scenario to follow or role to play can be helpful for complex queries or when seeking creative responses. Using a hypothetical prompt, you set up a situation, problem, or story, then ask the model to respond as if it were a character in that scenario or an expert on the topic.

Example scenario prompt:

```text
Your role is to extract the name of the author from any given text

“Some humans theorize that intelligent species go extinct before they can expand into outer space. If they're correct, then the hush of the night sky is the silence of the graveyard.”
― Ted Chiang, Exhalation
```

Output:

```text
 Ted Chiang
```

### Demonstration prompt example (few-shot learning)

Similar to completion-style prompts, demonstrations show the model what to do. This approach is sometimes called few-shot learning, as the model learns from a few examples provided in the prompt.

Example demonstration prompt:

```text
Quote:
“When the reasoning mind is forced to confront the impossible again and again, it has no choice but to adapt.”
― N.K. Jemisin, The Fifth Season
Author: N.K. Jemisin

Quote:
“Some humans theorize that intelligent species go extinct before they can expand into outer space. If they're correct, then the hush of the night sky is the silence of the graveyard.”
― Ted Chiang, Exhalation
Author:
```

Output:

```text
 Ted Chiang
```

### Fine-tuned prompt example

With enough examples, you can [fine-tune][Fine Tuning Docs] a custom model. In this case, instructions become unnecessary. However, it can be helpful to include separator sequences (e.g., `->` or `###` or any string that doesn't commonly appear in your inputs) to tell the model when the prompt has ended and the output should begin. Without separator sequences, the model may continue elaborating, rather than generating what you want to see.

Example fine-tuned prompt (for a model that has been custom trained on similar prompt-completion pairs):

```text
“Some humans theorize that intelligent species go extinct before they can expand into outer space. If they're correct, then the hush of the night sky is the silence of the graveyard.”
― Ted Chiang, Exhalation

###


```

Output:

```text
 Ted Chiang
```

## Code Capabilities

Large language models aren't only great at text - they can be great at code too. OpenAI's [GPT-4][GPT-4 and GPT-4 Turbo] model is a prime example.

GPT-4 powers [numerous innovative products][OpenAI Customer Stories], including:

- [GitHub Copilot] (autocompletes code in Visual Studio and other IDEs)
- [Replit](https://replit.com/) (can complete, explain, edit and generate code)
- [Cursor](https://cursor.sh/) (build software faster in an editor designed for pair-programming with AI)

GPT-4 is more advanced than previous models like `gpt-3.5-turbo-instruct`. But, to get the best out of GPT-4 for coding tasks, it's still important to give clear and specific instructions. As a result, designing good prompts can take more care.

### More prompt advice

For more prompt examples, visit [OpenAI Examples][OpenAI Examples].

In general, the input prompt is the best lever for improving model outputs. You can try tricks like:

- **Be specific** If you want the output to be a comma separated list, ask the LLM to return a comma separated list. If you want it to say "I don't know" when it doesn't know the answer, tell it 'Say "I don't know" if you do not know the answer.' The more specific your instructions, the better the model can respond.
- **Provide Context**: Help the model understand the bigger picture of your request. This could be background information, examples/demonstrations of what you want or explaining the purpose of your task.
- **Ask the model to answer as if it was an expert.** Explicitly asking the model to produce high quality output or output as if it was written by an expert can induce the model to give higher quality answers that it thinks an expert would write. Phrases like "Explain in detail" or "Describe step-by-step" can be effective.
- **Prompt the model to write down the series of steps explaining its reasoning.** If understanding the 'why' behind an answer is important, prompt the model to include its reasoning. This can be done by simply adding a line like "[Let's think step by step](https://arxiv.org/abs/2205.11916)" before each answer.

[Fine Tuning Docs]: https://platform.openai.com/docs/guides/fine-tuning
[OpenAI Customer Stories]: https://openai.com/customer-stories
[Large language models Blog Post]: https://openai.com/research/better-language-models
[GitHub Copilot]: https://github.com/features/copilot/
[GPT-4 and GPT-4 Turbo]: https://platform.openai.com/docs/models/gpt-4-and-gpt-4-turbo
[GPT3 Apps Blog Post]: https://openai.com/blog/gpt-3-apps/
[OpenAI Examples]: https://platform.openai.com/examples
