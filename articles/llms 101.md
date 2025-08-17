# LLMs 101: What Even Is It?
---
### Preface

Large language models (LLMs) are artificial neural networks trained on vast amounts of text. The most common type is the **transformer**, introduced in the 2017 paper _Attention Is All You Need_. Transformers break text into smaller units called **tokens**, turn those into numbers, run them through layers of matrix math and attention, and then predict what tokens come next.

OpenAI’s ChatGPT, built on GPT-3, brought this architecture into the spotlight and kicked off today’s wave of AI applications.

---
### What can LLMs do?

Although they’re called _language_ models, LLMs can handle many kinds of data if trained for it. For text, typical uses include:

- Generating text    
- Completing text
- Translating text
- Analyzing or summarizing text
- Answering questions
- Powering agents that perform tasks

This Cookbook focuses on the first few, since they’re the foundation of most real-world applications.

---
### How do they work?

At their core, LLMs are **prediction engines**. Given some input text, they predict the most likely next token, then the next, and so on until they produce a coherent output.

Tokens live in an **embedding space**—a mathematical map where related concepts sit near one another. For example, _king_ and _queen_ are neighbors, just as _emperor_ and _empress_ are. This structure allows the model to capture relationships and context when generating text.

---
### **Why it matters for you**

You don’t need every detail of the math to use LLMs effectively. The key takeaway is simple:
**LLMs generate outputs by predicting one token at a time.**

The rest of this Cookbook will show you how to harness that prediction power—whether you want to generate text, complete thoughts, or analyze documents.