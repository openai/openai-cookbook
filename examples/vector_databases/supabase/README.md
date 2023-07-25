# Supabase Vector (Postgres with pgvector)

Supabase provides an [open source toolkit](https://supabase.com/docs/guides/ai) for developing AI applications using Postgres and pgvector. Use the Supabase client libraries to store, index, and query your vector embeddings at scale.

The toolkit includes:

- A [vector store](https://supabase.com/docs/guides/ai/vector-columns) and embeddings support using Postgres and pgvector.
- A [Python client](https://supabase.com/docs/guides/ai/vecs-python-client) for managing unstructured embeddings.
- [Database migrations](https://supabase.com/docs/guides/ai/examples/headless-vector-search#prepare-your-database) for managing structured embeddings.
- Integrations with all popular AI providers, such as [OpenAI](https://supabase.com/docs/guides/ai/examples/openai), [Hugging Face](https://supabase.com/docs/guides/ai/hugging-face), [LangChain](https://supabase.com/docs/guides/ai/langchain), and more.

## Examples

This folder contains examples of using Supabase and OpenAI together. More will be added over time so check back for updates or review the [Supabase doc](https://supabase.com/docs/guides/ai) for additional information!

| Name                                                      | Description                                                                | Google Colab                                                                                                                                                                                                                   |
| --------------------------------------------------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| [Hello World](./vector_hello_world.ipynb)                 | Basic "Hello World" example with Supabase Vecs.                            | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/openai/openai-cookbook/blob/master/examples/vector_databases/supabase/vector_hello_world.ipynb)          |
| [Text Deduplication](./semantic_text_deduplication.ipynb) | Finding duplicate movie reviews with Supabase Vecs.                        | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/openai/openai-cookbook/blob/master/examples/vector_databases/supabase/semantic_text_deduplication.ipynb) |
| [Face similarity search](./face_similarity.ipynb)         | Identify the celebrities who look most similar to you using Supabase Vecs. | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/openai/openai-cookbook/blob/master/examples/vector_databases/supabase/face_similarity.ipynb)             |
