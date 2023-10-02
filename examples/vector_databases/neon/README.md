# What is Neon?

[Neon](https://neon.tech/) is Serverless Postgres built for the cloud. Neon separates compute and storage to offer modern developer features such as autoscaling, database branching, scale-to-zero, and more.

## Vector search

Neon supports vector search using the [pgvector](https://neon.tech/docs/extensions/pgvector) open-source PostgreSQL extension, which enables Postgres as a vector database for storing and querying embeddings.

## OpenAI cookbook notebook

Check out the notebook in this repo for working with Neon Serverless Postgres as your vector database.

### Semantic search using Neon Postgres with pgvector and OpenAI

In this notebook you will learn how to:

1. Use embeddings created by OpenAI API
2. Store embeddings in a Neon Serverless Postgres database
3. Convert a raw text query to an embedding with OpenAI API
4. Use Neon with the `pgvector` extension to perform vector similarity search

## Scaling Support

Neon enables you to scale your AI applications with the following features:

- [Autoscaling](https://neon.tech/docs/introduction/read-replicas): If your AI application experiences heavy load during certain hours of the day or at different times, Neon can automatically scale compute resources without manual intervention. During periods of inactivity, Neon is able to scale to zero.
- [Instant read replicas](https://neon.tech/docs/introduction/read-replicas): Neon supports instant read replicas, which are independent read-only compute instances designed to perform read operations on the same data as your read-write computes. With read replicas, you can offload reads from your read-write compute instance to a dedicated read-only compute instance for your AI application.
- [The Neon serverless driver](https://neon.tech/docs/serverless/serverless-driver): Neon supports a low-latency serverless PostgreSQL driver for JavaScript and TypeScript applications that allows you to query data from serverless and edge environments, making it possible to achieve sub-10ms queries.

## More Examples

- [Build an AI-powered semantic search application](https://github.com/neondatabase/yc-idea-matcher) - Submit a startup idea and get a list of similar ideas that YCombinator has invested in before
- [Build an AI-powered chatbot](https://github.com/neondatabase/ask-neon) - A Postgres Q&A chatbot that uses Postgres as a vector database
- [Vercel Postgres pgvector Starter](https://vercel.com/templates/next.js/postgres-pgvector) - Vector similarity search with Vercel Postgres (powered by Neon)

## Additional Resources

- [Building AI applications with Neon](https://neon.tech/ai)
- [Neon AI & embeddings documentation](https://neon.tech/docs/ai/ai-intro)
- [Building an AI-powered Chatbot using Vercel, OpenAI, and Postgres](neon.tech/blog/building-an-ai-powered-chatbot-using-vercel-openai-and-postgres)
- [Web-based AI SQL Playground and connecting to Postgres from the browser](https://neon.tech/blog/postgres-ai-playground)
- [pgvector GitHub repository](https://github.com/pgvector/pgvector)
