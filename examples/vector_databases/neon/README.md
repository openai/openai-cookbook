# What is Neon?

[Neon](https://neon.tech/) is open-source serverless Postgres built for the cloud. Neon separates compute and storage to offer modern developer features such as autoscaling, database branching, scale-to-zero, and more.

## Vector search

Neon supports vector search through the [pg_embedding](https://neon.tech/docs/extensions/pg_embedding) and [pgvector](https://neon.tech/docs/extensions/pgvector) open-source PostgreSQL extensions, both of which allow you to enable Postgres as a vector database for storing and querying embeddings.

## pg_embedding

The pg_embedding extension, developed and maintained by Neon, enables storing vector embeddings and graph-based vector similarity search in Postgres using the Hierarchical Navigable Small World (HNSW) algorithm. It supports HNSW indexes, which enable new levels of efficiency in high-dimensional similarity search, allowing you to scale your AI applications to millions of rows. Supported distance metrics include L2 (`<->`), cosine (`<=>`), and Manhattan (`<~>`). For more information, see [The pg_embedding extension](https://neon.tech/docs/extensions/pg_embedding).

## pgvector

The pgvector extension enables storing vector embeddings and vector similarity search in Postgres. It supports `ivfflat` indexes. For more information, see [The pgvector extension](https://neon.tech/docs/extensions/pgvector). Supported distance metrics include L2 (`<->`), inner product (`<#>`), and cosine (`<=>`).

## Scaling Support

Neon enables you to scale your AI applications with the following features:

- [Autoscaling](https://neon.tech/docs/introduction/read-replicas): If your AI application experiences heavy load during certain hours of the day or at different times throughout the week, month, or calendar year, Neon automatically scales compute resources without manual intervention according to the compute size boundaries that you define. During periods of inactivity, Neon is able to scale to zero.
- [Instant read replicas](https://neon.tech/docs/introduction/read-replicas): Neon supports instant read replicas, which are independent read-only compute instances designed to perform read operations on the same data as your read-write computes. With read replicas, you can offload reads from your read-write compute instance to a dedicated read-only compute instance for your AI application.
- [The Neon serverless driver](https://neon.tech/docs/serverless/serverless-driver): Neon supports a low-latency serverless PostgreSQL driver for JavaScript and TypeScript applications that allows you to query data from serverless and edge environments, making it possible to achieve sub-10ms  queries.

## Examples

- [Build an AI-powered semantic search application](https://github.com/neondatabase/yc-idea-matcher) - Submit a startup idea and get a list of similar ideas that YCombinator has invested in before
- [Build an AI-powered chatbot](https://github.com/neondatabase/ask-neon) - A Postgres Q&A chatbot that uses Postgres as a vector database
- [Vercel Postgres pgvector Starter](https://vercel.com/templates/next.js/postgres-pgvector) - Vector similarity search with Vercel Postgres (powered by Neon)

## Additional Resources

- [Building AI applications with Neon](https://neon.tech/ai)
- [Neon AI & embeddings documentation](https://neon.tech/docs/ai/ai-intro)
- [Building an AI-powered ChatBot using Vercel, OpenAI, and Postgres](neon.tech/blog/building-an-ai-powered-chatbot-using-vercel-openai-and-postgres)
- [Web-based AI SQL Playground and connecting to Postgres from the browser](https://neon.tech/blog/postgres-ai-playground)
- [pg_embedding GitHub repository](https://github.com/neondatabase/pg_embedding)
- [pgvector GitHub repository](https://github.com/pgvector/pgvector)
