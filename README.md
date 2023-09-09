# OpenAI Cookbook

The OpenAI Cookbook shares example code for accomplishing common tasks with the [OpenAI API].

To run these examples, you'll need an OpenAI account and API key ([create a free account][api signup]).

Most code examples are written in Python, though the concepts can be applied in any language.

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://github.com/codespaces/new?hide_repo_select=true&ref=main&repo=468576060&machine=basicLinux32gb&location=EastUs)

## Recently added/updated 🆕 ✨
- [How to fine-tune chat models](https://github.com/openai/openai-cookbook/blob/main/examples/How_to_finetune_chat_models.ipynb) [Aug 22, 2023]
- [How to evaluate abstractive summarization](examples/evaluation/How_to_eval_abstractive_summarization.ipynb) [Aug 16, 2023]
- [Whisper prompting guide](examples/Whisper_prompting_guide.ipynb) [June 27, 2023]
- [Question answering using a search API and re-ranking](https://github.com/openai/openai-cookbook/blob/main/examples/Question_answering_using_a_search_API.ipynb) [June 16, 2023]
- [How to call functions with Chat models](https://github.com/openai/openai-cookbook/blob/main/examples/How_to_call_functions_with_chat_models.ipynb) [June 13, 2023]

## Guides & examples

- API usage
  - [How to handle rate limits](examples/How_to_handle_rate_limits.ipynb)
    - [Example parallel processing script that avoids hitting rate limits](examples/api_request_parallel_processor.py)
  - [How to count tokens with tiktoken](examples/How_to_count_tokens_with_tiktoken.ipynb)
- GPT
  - [How to format inputs to ChatGPT models](examples/How_to_format_inputs_to_ChatGPT_models.ipynb)
  - [How to stream completions](examples/How_to_stream_completions.ipynb)
  - [How to use a multi-step prompt to write unit tests](examples/Unit_test_writing_using_a_multi-step_prompt.ipynb)
  - [Guide: How to work with large language models](how_to_work_with_large_language_models.md)
  - [Guide: Techniques to improve reliability](techniques_to_improve_reliability.md)
- Embeddings
  - [Text comparison examples](text_comparison_examples.md)
  - [How to get embeddings](examples/Get_embeddings.ipynb)
  - [Question answering using embeddings](examples/Question_answering_using_embeddings.ipynb)
  - [Using vector databases for embeddings search](examples/vector_databases)
  - [Semantic search using embeddings](examples/Semantic_text_search_using_embeddings.ipynb)
  - [Recommendations using embeddings](examples/Recommendation_using_embeddings.ipynb)
  - [Clustering embeddings](examples/Clustering.ipynb)
  - [Visualizing embeddings in 2D](examples/Visualizing_embeddings_in_2D.ipynb) or [3D](examples/Visualizing_embeddings_in_3D.ipynb)
  - [Embedding long texts](examples/Embedding_long_inputs.ipynb)
  - [Embeddings playground (streamlit app)](apps/embeddings-playground/README.md)
  - [Search reranking with cross-encoders](examples/Search_reranking_with_cross-encoders.ipynb)
- Apps
  - [File Q&A](apps/file-q-and-a/)
  - [Web Crawl Q&A](apps/web-crawl-q-and-a)
  - [Powering your products with ChatGPT and your own data](apps/chatbot-kickstarter/powering_your_products_with_chatgpt_and_your_data.ipynb)
- Fine-tuning GPT-3
  - [Guide: best practices for fine-tuning GPT-3 to classify text](https://docs.google.com/document/d/1rqj7dkuvl7Byd5KQPUJRxc19BJt8wo0yHNwK84KfU3Q/edit)
  - [Fine-tuned classification](examples/Fine-tuned_classification.ipynb)
- DALL-E
  - [How to generate and edit images with DALL·E](examples/dalle/Image_generations_edits_and_variations_with_DALL-E.ipynb)
  - [How to create dynamic masks with DALL·E and Segment Anything](examples/dalle/How_to_create_dynamic_masks_with_DALL-E_and_Segment_Anything.ipynb)
- Whisper
  - [Whisper prompting guide](examples/Whisper_prompting_guide.ipynb)
- Azure OpenAI (alternative API from Microsoft Azure)
  - [How to use ChatGPT with Azure OpenAI](examples/azure/chat.ipynb)
  - [How to get completions from Azure OpenAI](examples/azure/completions.ipynb)
  - [How to get embeddings from Azure OpenAI](examples/azure/embeddings.ipynb)
  - [How to generate images with DALL·E fom Azure OpenAI](examples/azure/DALL-E.ipynb)

## Related OpenAI resources

Beyond the code examples here, you can learn about the [OpenAI API] from the following resources:

- Experiment with [ChatGPT]
- Try the API in the [OpenAI Playground]
- Read about the API in the [OpenAI Documentation]
- Get help in the [OpenAI Help Center]
- Discuss the API in the [OpenAI Community Forum] or [OpenAI Discord channel]
- See example prompts in the [OpenAI Examples]
- Stay updated with the [OpenAI Blog]

## Related resources from around the web

People are writing great tools and papers for improving outputs from GPT. Here are some cool ones we've seen:

### Prompting libraries & tools

- [Guidance](https://github.com/microsoft/guidance): A handy looking Python library from Microsoft that uses Handlebars templating to interleave generation, prompting, and logical control.
- [LangChain](https://github.com/hwchase17/langchain): A popular Python/JavaScript library for chaining sequences of language model prompts.
- [FLAML (A Fast Library for Automated Machine Learning & Tuning)](https://microsoft.github.io/FLAML/docs/Getting-Started/): A Python library for automating selection of models, hyperparameters, and other tunable choices.
- [Chainlit](https://docs.chainlit.io/overview): A Python library for making chatbot interfaces.
- [Guardrails.ai](https://shreyar.github.io/guardrails/): A Python library for validating outputs and retrying failures. Still in alpha, so expect sharp edges and bugs.
- [Semantic Kernel](https://github.com/microsoft/semantic-kernel): A Python/C#/Java library from Microsoft that supports prompt templating, function chaining, vectorized memory, and intelligent planning.
- [Prompttools](https://github.com/hegelai/prompttools): Open-source Python tools for testing and evaluating models, vector DBs, and prompts.
- [Outlines](https://github.com/normal-computing/outlines): A Python library that provides a domain-specific language to simplify prompting and constrain generation.
- [Promptify](https://github.com/promptslab/Promptify): A small Python library for using language models to perform NLP tasks.
- [Scale Spellbook](https://scale.com/spellbook): A paid product for building, comparing, and shipping language model apps.
- [PromptPerfect](https://promptperfect.jina.ai/prompts): A paid product for testing and improving prompts.
- [Weights & Biases](https://wandb.ai/site/solutions/llmops): A paid product for tracking model training and prompt engineering experiments.
- [OpenAI Evals](https://github.com/openai/evals): An open-source library for evaluating task performance of language models and prompts.
- [LlamaIndex](https://github.com/jerryjliu/llama_index): A Python library for augmenting LLM apps with data.
- [Arthur Shield](https://www.arthur.ai/get-started): A paid product for detecting toxicity, hallucination, prompt injection, etc.
- [LMQL](https://lmql.ai): A programming language for LLM interaction with support for typed prompting, control flow, constraints, and tools.

### Prompting guides

- [Brex's Prompt Engineering Guide](https://github.com/brexhq/prompt-engineering): Brex's introduction to language models and prompt engineering.
- [promptingguide.ai](https://www.promptingguide.ai/): A prompt engineering guide that demonstrates many techniques.
- [OpenAI Cookbook: Techniques to improve reliability](https://github.com/openai/openai-cookbook/blob/main/techniques_to_improve_reliability.md): A slightly dated (Sep 2022) review of techniques for prompting language models.
- [Lil'Log Prompt Engineering](https://lilianweng.github.io/posts/2023-03-15-prompt-engineering/): An OpenAI researcher's review of the prompt engineering literature (as of March 2023).
- [learnprompting.org](https://learnprompting.org/): An introductory course to prompt engineering.

### Video courses

- [Andrew Ng's DeepLearning.AI](https://www.deeplearning.ai/short-courses/chatgpt-prompt-engineering-for-developers/): A short course on prompt engineering for developers.
- [Andrej Karpathy's Let's build GPT](https://www.youtube.com/watch?v=kCc8FmEb1nY): A detailed dive into the machine learning underlying GPT.
- [Prompt Engineering by DAIR.AI](https://www.youtube.com/watch?v=dOxUroR57xs): A one-hour video on various prompt engineering techniques.

### Papers on advanced prompting to improve reasoning

- [Chain-of-Thought Prompting Elicits Reasoning in Large Language Models (2022)](https://arxiv.org/abs/2201.11903): Using few-shot prompts to ask models to think step by step improves their reasoning. PaLM's score on math word problems (GSM8K) rises from 18% to 57%.
- [Self-Consistency Improves Chain of Thought Reasoning in Language Models (2022)](https://arxiv.org/abs/2203.11171): Taking votes from multiple outputs improves accuracy even more. Voting across 40 outputs raises PaLM's score on math word problems further, from 57% to 74%, and `code-davinci-002`'s from 60% to 78%.
- [Tree of Thoughts: Deliberate Problem Solving with Large Language Models (2023)](https://arxiv.org/abs/2305.10601): Searching over trees of step by step reasoning helps even more than voting over chains of thought. It lifts `GPT-4`'s scores on creative writing and crosswords.
- [Language Models are Zero-Shot Reasoners (2022)](https://arxiv.org/abs/2205.11916): Telling instruction-following models to think step by step improves their reasoning. It lifts `text-davinci-002`'s score on math word problems (GSM8K) from 13% to 41%.
- [Large Language Models Are Human-Level Prompt Engineers (2023)](https://arxiv.org/abs/2211.01910): Automated searching over possible prompts found a prompt that lifts scores on math word problems (GSM8K) to 43%, 2 percentage points above the human-written prompt in Language Models are Zero-Shot Reasoners.
- [Reprompting: Automated Chain-of-Thought Prompt Inference Through Gibbs Sampling (2023)](https://arxiv.org/abs/2305.09993): Automated searching over possible chain-of-thought prompts improved ChatGPT's scores on a few benchmarks by 0–20 percentage points.
- [Faithful Reasoning Using Large Language Models (2022)](https://arxiv.org/abs/2208.14271): Reasoning can be improved by a system that combines: chains of thought generated by alternative selection and inference prompts, a halter model that chooses when to halt selection-inference loops, a value function to search over multiple reasoning paths, and sentence labels that help avoid hallucination.
- [STaR: Bootstrapping Reasoning With Reasoning (2022)](https://arxiv.org/abs/2203.14465): Chain of thought reasoning can be baked into models via fine-tuning. For tasks with an answer key, example chains of thoughts can be generated by language models.
- [ReAct: Synergizing Reasoning and Acting in Language Models (2023)](https://arxiv.org/abs/2210.03629): For tasks with tools or an environment, chain of thought works better you prescriptively alternate between **Re**asoning steps (thinking about what to do) and **Act**ing (getting information from a tool or environment).
- [Reflexion: an autonomous agent with dynamic memory and self-reflection (2023)](https://arxiv.org/abs/2303.11366): Retrying tasks with memory of prior failures improves subsequent performance.
- [Demonstrate-Search-Predict: Composing retrieval and language models for knowledge-intensive NLP (2023)](https://arxiv.org/abs/2212.14024): Models augmented with knowledge via a "retrieve-then-read" can be improved with multi-hop chains of searches.
- [Improving Factuality and Reasoning in Language Models through Multiagent Debate (2023)](https://arxiv.org/abs/2305.14325): Generating debates between a few ChatGPT agents over a few rounds improves scores on various benchmarks. Math word problem scores rise from 77% to 85%.

## Contributing

If there are examples or guides you'd like to see, feel free to suggest them on the [issues page]. We are also happy to accept high quality pull requests, as long as they fit the scope of the repo.

[chatgpt]: https://chat.openai.com/
[openai api]: https://openai.com/api/
[api signup]: https://beta.openai.com/signup
[openai playground]: https://beta.openai.com/playground
[openai documentation]: https://beta.openai.com/docs/introduction
[openai community forum]: https://community.openai.com/top?period=monthly
[openai discord channel]: https://discord.com/invite/openai
[openai help center]: https://help.openai.com/en/
[openai examples]: https://beta.openai.com/examples
[openai blog]: https://openai.com/blog/
[issues page]: https://github.com/openai/openai-cookbook/issues
