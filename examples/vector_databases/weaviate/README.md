# Weaviate <> OpenAI

[​Weaviate](https://weaviate.io) is an open-source vector search engine ([docs](https://weaviate.io/developers/weaviate) - [Github](https://github.com/weaviate/weaviate)) that can store and search through OpenAI embeddings _and_ data objects. The database allows you to do similarity search, hybrid search (the combining of multiple search techniques, such as keyword-based and vector search), and generative search (like Q&A). Weaviate also supports a wide variety of OpenAI-based modules (e.g., [`text2vec-openai`](https://weaviate.io/developers/weaviate/modules/retriever-vectorizer-modules/text2vec-openai), [`qna-openai`](https://weaviate.io/developers/weaviate/modules/reader-generator-modules/qna-openai)), allowing you to vectorize and query data fast and efficiently.

You can run Weaviate (including the OpenAI modules if desired) in three ways:

1. Open source inside a Docker-container ([example](./docker-compose.yml))
2. Using the Weaviate Cloud Service ([get started](https://weaviate.io/developers/weaviate/quickstart/installation#weaviate-cloud-service))
3. In a Kubernetes cluster ([learn more](https://weaviate.io/developers/weaviate/installation/kubernetes))

### Examples

This folder contains a variety of Weaviate and OpenAI examples. 

| Name | Description | language | Google Colab |
| --- | --- | --- | --- |
| [Getting Started with Weaviate and OpenAI](./getting-started-with-weaviate-and-openai.ipynb) | A simple getting started for *semantic vector search* using the OpenAI vectorization module in Weaviate (`text2vec-openai`) | Python Notebook | [link](https://colab.research.google.com/drive/1RxpDE_ruCnoBB3TfwAZqdjYgHJhtdwhK) |
| [Hybrid Search with Weaviate and OpenAI](./hybrid-search-with-weaviate-and-openai.ipynb) | A simple getting started for *hybrid search* using the OpenAI vectorization module in Weaviate (`text2vec-openai`) | Python Notebook | [link](https://colab.research.google.com/drive/1E75BALWoKrOjvUhaznJKQO0A-B1QUPZ4) |
| [Question Answering with Weaviate and OpenAI](./question-answering-with-weaviate-and-openai.ipynb) | A simple getting started for *question answering (Q&A)* using the OpenAI Q&A module in Weaviate (`qna-openai`) | Python Notebook | [link](https://colab.research.google.com/drive/1pUerUZrJaknEboDxDxsuf3giCK0MJJgm) |
| [Docker-compose example](./docker-compose.yml) | A Docker-compose file with all OpenAI modules enabled | Docker |
