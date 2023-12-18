# Supabase Vector Database

[Supabase](https://supabase.com/docs) is an open-source Firebase alternative built on top of [Postgres](https://en.wikipedia.org/wiki/PostgreSQL), a production-grade SQL database.

[Supabase Vector](https://supabase.com/docs/guides/ai) is a vector toolkit built on [pgvector](https://github.com/pgvector/pgvector), a Postgres extension that allows you to store your embeddings inside the same database that holds the rest of your application data. When combined with pgvector's indexing algorithms, vector search remains [fast at large scales](https://supabase.com/blog/increase-performance-pgvector-hnsw).

Supabase adds an ecosystem of services and tools on top of Postgres that makes app development as quick as possible, including:

- [Auto-generated REST APIs](https://supabase.com/docs/guides/api)
- [Auto-generated GraphQL APIs](https://supabase.com/docs/guides/graphql)
- [Realtime APIs](https://supabase.com/docs/guides/realtime)
- [Authentication](https://supabase.com/docs/guides/auth)
- [File storage](https://supabase.com/docs/guides/storage)
- [Edge functions](https://supabase.com/docs/guides/functions)

We can use these services alongside pgvector to store and query embeddings within Postgres.

## OpenAI Cookbook Examples

Below are guides and resources that walk you through how to use OpenAI embedding models with Supabase Vector.

| Guide                                    | Description                                                |
| ---------------------------------------- | ---------------------------------------------------------- |
| [Semantic search](./semantic-search.mdx) | Store, index, and query embeddings at scale using pgvector |

## Additional resources

- [Vector columns](https://supabase.com/docs/guides/ai/vector-columns)
- [Vector indexes](https://supabase.com/docs/guides/ai/vector-indexes)
- [RAG with permissions](https://supabase.com/docs/guides/ai/rag-with-permissions)
- [Going to production](https://supabase.com/docs/guides/ai/going-to-prod)
- [Deciding on compute](https://supabase.com/docs/guides/ai/choosing-compute-addon)
