# LangChain, OpenAI, and Oracle AI Database for Vector Search

This example shows how to build a semantic search workflow using:

- **OpenAI embeddings** for turning text into vector representations
- **LangChain’s Oracle vector store integration** for working with vectors through a familiar framework abstraction
- **Oracle AI Database Vector Search** for storing embeddings and retrieving relevant content with similarity search

If you are looking for a practical starting point for **LangChain + Oracle AI Database**, **OpenAI embeddings with Oracle Vector Search**, or a developer-friendly example of semantic retrieval that integrates directly with data stored in Oracle AI Database, this notebook is designed to be easy to read, run, and adapt.

## Why this stack works well

This combination is useful because each component solves a different part of the workflow:

- **OpenAI embeddings** convert text into semantic vectors that capture meaning beyond keyword matching
- **LangChain** provides a developer-friendly abstraction for vector stores and retrieval workflows
- **Oracle AI Database** stores vectors alongside application and relational data, making it easier to build retrieval-enabled applications without introducing a separate vector database

For developers evaluating semantic search patterns, this creates a practical setup that is easy to prototype locally and extend later into larger RAG or agent-based workflows.

## Why use Oracle AI Database with LangChain

Oracle AI Database is a strong fit for LangChain-based vector workflows when you want:

- **vector search and application data in one place**
- **less infrastructure complexity**, especially for teams already using Oracle
- **native SQL access to vector operations**
- **a smoother path from notebook prototype to production architecture**
- compatibility with **LangChain retrieval patterns**, while keeping Oracle AI Database as the retrieval backbone

This is especially helpful when vector search is not a standalone demo, but one part of a broader enterprise or application stack.

## What you will learn

By working through the notebook, you will learn how to:

- connect to Oracle AI Database from Python
- configure OpenAI embeddings for semantic search
- initialize LangChain’s Oracle vector store integration
- store sample documents and embeddings in Oracle AI Database
- run vector similarity search against indexed content
- inspect how LangChain retrieval maps to Oracle AI Database Vector Search
- use the same pattern as a baseline for larger retrieval or RAG workflows

## Architecture at a glance

The example follows a simple semantic retrieval flow:

1. Load configuration and environment variables
2. Initialize OpenAI embeddings
3. Connect to Oracle AI Database
4. Initialize the LangChain Oracle vector store
5. Insert sample text documents
6. Convert the query into an embedding
7. Run vector similarity search
8. Return the most relevant matching content

In a larger application, this same pattern can become the retrieval layer behind a RAG pipeline, internal search assistant, or AI agent workflow.

## Prerequisites

You will need:

- **Oracle AI Database** with Vector Search enabled
- **OpenAI API key**
- **Python 3.10+**
- Notebook dependencies installed for this example

## Environment variables

Create a local `.env` file and provide values similar to the following:

```env
OPENAI_API_KEY=
ORACLE_USER=PDBADMIN
ORACLE_PASSWORD=YourPassword
ORACLE_DSN=localhost:1521/FREEPDB1
```

## Python dependencies
Install the required packages using pip:

```bash
pip install langchain
pip install langchain-openai
pip install langchain-oracledb
pip install oracledb
pip install python-dotenv
```


## Files in this example

- `oracle_vector_search_langchain.ipynb` — the main notebook demonstrating semantic search with LangChain, OpenAI, and Oracle AI Database
- `.env` — local configuration file for OpenAI and Oracle connection settings



## How to run

1. Set your `OPENAI_API_KEY` in the local `.env` file
2. Make sure your Oracle AI Database instance is running and the connection values are correct
3. Open `oracle_vector_search_langchain.ipynb`
4. Run the notebook cells in order

The notebook walks through dependency setup, embedding initialization, Oracle database connection, vector store creation, sample document ingestion, and semantic similarity search.


## Expected outcome

By the end of this notebook, you will have a working semantic search example where:

- text is converted into embeddings using OpenAI
- vectors are stored in Oracle AI Database
- LangChain interacts with Oracle AI Database through its vector store integration
- similarity search returns the most relevant documents for a given query

This can serve as a baseline for larger retrieval, RAG, or agent-based applications.

## Next steps

Once this example is working, you can extend it by:

- replacing the sample documents with your own data
- adding metadata and document chunking
- using the same retrieval flow in a larger RAG pipeline
- integrating the notebook logic into an API or application


## Documentation
For additional information, please refer to the documentation:

[![LangChain Oracle Vector Store](https://img.shields.io/badge/LangChain-Oracle%20Vector%20Store-blue)](https://docs.langchain.com/oss/python/integrations/vectorstores/oracle)
[![LangChain OpenAI Embeddings](https://img.shields.io/badge/LangChain-OpenAI%20Embeddings-green)](https://docs.langchain.com/oss/python/integrations/text_embedding/openai)
[![Oracle Database Vector Search](https://img.shields.io/badge/Oracle-Database%20Vector%20Search-red)](https://docs.oracle.com/en/database/oracle/oracle-database/26/vecse/)

