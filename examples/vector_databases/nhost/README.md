# What is Nhost?

[Nhost](https://nhost.io/) is an enterprise-grade open-source backend platform built on top of GraphQL & PostgreSQL. Nhost offers the convenience of Firebase, with the extensibility of platforms like Render and Heroku.

Nhost is a great choice for full-stack teams that want to get out of the ground fast, but also want to have the flexibility to customize their backend as they grow.

## Vector search and PostgreSQL

Nhost supports vector search using the [pgvector](https://docs.nhost.io/guides/database/extensions#pgvector) open-source PostgreSQL extension. With `pgvector`, you can store and query high-dimensional vectors alongside your application data.

In this guide, we leverage Graphite, an AI service from the Nhost stack that automatically generates and keeps your embeddings up-to-date.

### Semantic search with Nhost Postgres and OpenAI

In this notebook you will learn how to:

1. Run a development instance of Nhost Postgres with the `pgvector` extension.
2. Leverage Auto-Embeddings & OpenAI to generate and keep your embeddings up-to-date automatically.
3. Perform semantic search using natural language and GraphQL.

## Additional Resources

- [Nhost AI product page](https://nhost.io/product/graphite)
- [Nhost AI documentation](https://docs.nhost.io/product/ai)
- [pgvector GitHub repository](https://github.com/pgvector/pgvector)
