# Related resources from around the web

People are writing great tools and papers for improving outputs from GPT. Here are some cool ones we've seen:

## Prompting libraries & tools (in alphabetical order)

- [Arthur Shield](https://www.arthur.ai/get-started): A paid product for detecting toxicity, hallucination, prompt injection, etc.
- [Baserun](https://baserun.ai/): A paid product for testing, debugging, and monitoring LLM-based apps
- [Chainlit](https://docs.chainlit.io/overview): A Python library for making chatbot interfaces.
- [ElatoAI](https://github.com/akdeb/ElatoAI): A platform for running OpenAI Realtime API Speech on ESP32 on Arduino using Deno Edge Runtime and Supabase.
- [Embedchain](https://github.com/embedchain/embedchain): A Python library for managing and syncing unstructured data with LLMs.
- [FLAML (A Fast Library for Automated Machine Learning & Tuning)](https://microsoft.github.io/FLAML/docs/Getting-Started/): A Python library for automating selection of models, hyperparameters, and other tunable choices.
- [Guidance](https://github.com/microsoft/guidance): A handy looking Python library from Microsoft that uses Handlebars templating to interleave generation, prompting, and logical control.
- [Haystack](https://github.com/deepset-ai/haystack): Open-source LLM orchestration framework to build customizable, production-ready LLM applications in Python.
- [HoneyHive](https://honeyhive.ai): An enterprise platform to evaluate, debug, and monitor LLM apps.
- [LangChain](https://github.com/hwchase17/langchain): A popular Python/JavaScript library for chaining sequences of language model prompts.
- [LiteLLM](https://github.com/BerriAI/litellm): A minimal Python library for calling LLM APIs with a consistent format.
- [LlamaIndex](https://github.com/jerryjliu/llama_index): A Python library for augmenting LLM apps with data.
- [LLMOps Database](https://www.reddit.com/r/LocalLLaMA/comments/1h4u7au/a_nobs_database_of_how_companies_actually_deploy/): Database of how companies actually deploy LLMs in production.
- [LMQL](https://lmql.ai): A programming language for LLM interaction with support for typed prompting, control flow, constraints, and tools.
- [OpenAI Evals](https://github.com/openai/evals): An open-source library for evaluating task performance of language models and prompts.
- [Outlines](https://github.com/normal-computing/outlines): A Python library that provides a domain-specific language to simplify prompting and constrain generation.
- [Parea AI](https://www.parea.ai): A platform for debugging, testing, and monitoring LLM apps.
- [Portkey](https://portkey.ai/): A platform for observability, model management, evals, and security for LLM apps.
- [Promptify](https://github.com/promptslab/Promptify): A small Python library for using language models to perform NLP tasks.
- [PromptPerfect](https://promptperfect.jina.ai/prompts): A paid product for testing and improving prompts.
- [Prompttools](https://github.com/hegelai/prompttools): Open-source Python tools for testing and evaluating models, vector DBs, and prompts.
- [Scale Spellbook](https://scale.com/spellbook): A paid product for building, comparing, and shipping language model apps.
- [Semantic Kernel](https://github.com/microsoft/semantic-kernel): A Python/C#/Java library from Microsoft that supports prompt templating, function chaining, vectorized memory, and intelligent planning.
- [Vellum](https://www.vellum.ai/): A paid AI product development platform to experiment with, evaluate, and deploy advanced LLM apps.
- [Weights & Biases](https://wandb.ai/site/solutions/llmops): A paid product for tracking model training and prompt engineering experiments.
- [YiVal](https://github.com/YiVal/YiVal): An open-source GenAI-Ops tool for tuning and evaluating prompts, retrieval configurations, and model parameters using customizable datasets, evaluation methods, and evolution strategies.

## Prompting guides

- [Brex's Prompt Engineering Guide](https://github.com/brexhq/prompt-engineering): Brex's introduction to language models and prompt engineering.
- [learnprompting.org](https://learnprompting.org/): An introductory course to prompt engineering.
- [Lil'Log Prompt Engineering](https://lilianweng.github.io/posts/2023-03-15-prompt-engineering/): An OpenAI researcher's review of the prompt engineering literature (as of March 2023).
- [OpenAI Cookbook: Techniques to improve reliability](https://cookbook.openai.com/articles/techniques_to_improve_reliability): A slightly dated (Sep 2022) review of techniques for prompting language models.
- [promptingguide.ai](https://www.promptingguide.ai/): A prompt engineering guide that demonstrates many techniques.
- [Xavi Amatriain's Prompt Engineering 101 Introduction to Prompt Engineering](https://amatriain.net/blog/PromptEngineering) and [202 Advanced Prompt Engineering](https://amatriain.net/blog/prompt201): A basic but opinionated introduction to prompt engineering and a follow up collection with many advanced methods starting with CoT.

## Video courses

- [Andrew Ng's DeepLearning.AI](https://www.deeplearning.ai/short-courses/chatgpt-prompt-engineering-for-developers/): A short course on prompt engineering for developers.
- [Andrej Karpathy's Let's build GPT](https://www.youtube.com/watch?v=kCc8FmEb1nY): A detailed dive into the machine learning underlying GPT.
- [Prompt Engineering by DAIR.AI](https://www.youtube.com/watch?v=dOxUroR57xs): A one-hour video on various prompt engineering techniques.
- [Scrimba course about Assistants API](https://scrimba.com/learn/openaiassistants): A 30-minute interactive course about the Assistants API.
- [LinkedIn course: Introduction to Prompt Engineering: How to talk to the AIs](https://www.linkedin.com/learning/prompt-engineering-how-to-talk-to-the-ais/talking-to-the-ais?u=0): Short video introduction to prompt engineering

## Papers on advanced prompting to improve reasoning

- [Chain-of-Thought Prompting Elicits Reasoning in Large Language Models (2022)](https://arxiv.org/abs/2201.11903): Using few-shot prompts to ask models to think step by step improves their reasoning. PaLM's score on math word problems (GSM8K) rises from 18% to 57%.
- [Self-Consistency Improves Chain of Thought Reasoning in Language Models (2022)](https://arxiv.org/abs/2203.11171): Taking votes from multiple outputs improves accuracy even more. Voting across 40 outputs raises PaLM's score on math word problems further, from 57% to 74%, and `code-davinci-002`'s from 60% to 78%.
- [Tree of Thoughts: Deliberate Problem Solving with Large Language Models (2023)](https://arxiv.org/abs/2305.10601): Searching over trees of step by step reasoning helps even more than voting over chains of thought. It lifts `GPT-4`'s scores on creative writing and crosswords.
- [Language Models are Zero-Shot Reasoners (2022)](https://arxiv.org/abs/2205.11916): Telling instruction-following models to think step by step improves their reasoning. It lifts `text-davinci-002`'s score on math word problems (GSM8K) from 13% to 41%.
- [Large Language Models Are Human-Level Prompt Engineers (2023)](https://arxiv.org/abs/2211.01910): Automated searching over possible prompts found a prompt that lifts scores on math word problems (GSM8K) to 43%, 2 percentage points above the human-written prompt in Language Models are Zero-Shot Reasoners.
- [Reprompting: Automated Chain-of-Thought Prompt Inference Through Gibbs Sampling (2023)](https://arxiv.org/abs/2305.09993): Automated searching over possible chain-of-thought prompts improved ChatGPT's scores on a few benchmarks by 0–20 percentage points.
- [Faithful Reasoning Using Large Language Models (2022)](https://arxiv.org/abs/2208.14271): Reasoning can be improved by a system that combines: chains of thought generated by alternative selection and inference prompts, a halter model that chooses when to halt selection-inference loops, a value function to search over multiple reasoning paths, and sentence labels that help avoid hallucination.
- [STaR: Bootstrapping Reasoning With Reasoning (2022)](https://arxiv.org/abs/2203.14465): Chain of thought reasoning can be baked into models via fine-tuning. For tasks with an answer key, example chains of thoughts can be generated by language models.
- [ReAct: Synergizing Reasoning and Acting in Language Models (2023)](https://arxiv.org/abs/2210.03629): For tasks with tools or an environment, chain of thought works better if you prescriptively alternate between **Re**asoning steps (thinking about what to do) and **Act**ing (getting information from a tool or environment).
- [Reflexion: an autonomous agent with dynamic memory and self-reflection (2023)](https://arxiv.org/abs/2303.11366): Retrying tasks with memory of prior failures improves subsequent performance.
- [Demonstrate-Search-Predict: Composing retrieval and language models for knowledge-intensive NLP (2023)](https://arxiv.org/abs/2212.14024): Models augmented with knowledge via a "retrieve-then-read" can be improved with multi-hop chains of searches.
- [Improving Factuality and Reasoning in Language Models through Multiagent Debate (2023)](https://arxiv.org/abs/2305.14325): Generating debates between a few ChatGPT agents over a few rounds improves scores on various benchmarks. Math word problem scores rise from 77% to 85%.
