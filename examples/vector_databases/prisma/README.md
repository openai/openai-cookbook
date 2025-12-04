# What is Prisma Postgres?

[Prisma Postgres](https://pris.ly/Wd7WWHD) is a managed Postgres solution built for the cloud. Your app stays lightning-fast and responsive, whether you’re going from zero, or handling a spike. Free to start, pay when you grow.

## Vector search

Prisma Postgres supports vector search using the [pgvector](https://www.prisma.io/docs/postgres/database/postgres-extensions) open-source PostgreSQL extension, which enables Postgres as a vector database for storing and querying embeddings.

## OpenAI cookbook notebook

Check out the notebook in this repo for working with Prisma Postgres as your vector database.

### Semantic search using Prisma Postgres with pgvector and OpenAI

In this notebook you will learn how to:

1. Use embeddings created by OpenAI API
2. Store embeddings in a Prisma Postgres database
3. Convert a raw text query to an embedding with OpenAI API
4. Use Prisma Postgres with the `pgvector` extension to perform vector similarity search

## Scaling Support

Prisma Postgres enables you to scale your AI applications with the following features:

- Autoscaling: If your AI application experiences heavy load during certain hours of the day or at different times, Prisma can automatically scale compute resources without manual intervention. During periods of inactivity, Prisma is able to scale to zero.

- [The Prisma Postgres serverless driver](https://www.prisma.io/docs/postgres/database/serverless-driver): Prisma Postgres supports a low-latency serverless PostgreSQL driver for JavaScript and TypeScript applications that allows you to query data from serverless and edge environments.

## Additional Resources

- [Prisma MCP Server](https://www.prisma.io/mcp)
- [Prisma Postgres](https://www.prisma.io/postgres)
- [Vibe Coding with Limits — How to Build Apps in the Age of AI](https://www.prisma.io/blog/vibe-coding-with-limits-how-to-build-apps-in-the-age-of-ai)
- [pgvector GitHub repository](https://github.com/pgvector/pgvector)
