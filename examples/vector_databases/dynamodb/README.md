# Amazon DynamoDB

[Amazon DynamoDB](https://aws.amazon.com/dynamodb/) is a serverless, fully managed NoSQL database. Vector indexes add similarity search to a table: embeddings are stored as an ordinary attribute on the item, the index is declared as a property of the table, and the `SearchVectors` API queries it. There is no separate vector cluster to provision, and vectors live in the same table as the operational data they describe, written in the same `PutItem` call.

## What's here

- [`getting-started-with-amazon-dynamodb-and-openai.ipynb`](getting-started-with-amazon-dynamodb-and-openai.ipynb): create a table with a vector index, load Wikipedia articles with OpenAI embeddings, run similarity searches, enforce tenant isolation with search schemas, and feed retrieved context to a completion.
- [`docker-compose.yml`](docker-compose.yml): optional local backend for running the notebook without an AWS account.
- [`nbutils.py`](nbutils.py): helper to download the shared cookbook embeddings dataset.

## Running against Amazon DynamoDB

The notebook defaults to Amazon DynamoDB. You need an AWS account with credentials configured (environment variables, `aws configure`, or SSO) and `boto3>=1.43.64`, the first release with `SearchVectors` support. Loading the notebook's dataset costs a few cents with on-demand billing.

## Running locally

[ExtendDB](https://github.com/ExtendDB/extenddb) is an open-source DynamoDB-compatible engine maintained by engineers at AWS that supports vector indexes.

```bash
docker compose up -d
```

Then set `USE_LOCAL = True` in the notebook's configuration cell. The emulator enforces SigV4 with a fixed, publicly documented development credential, so no account or configuration is needed. The rest of the notebook is identical for both backends.

## Key concepts

| Concept | Detail |
|---------|--------|
| Vector storage | A list-of-numbers attribute on the item; no special type |
| Index declaration | `VectorIndexes` on `CreateTable` or `UpdateTable` |
| Distance functions | `COSINE`, `DOT_PRODUCT`, `EUCLIDEAN` |
| Query API | `SearchVectors` with `SearchVector`, `TopK`, optional `SearchConditionExpression` |
| Scoring | `Score` is the distance: lower is more similar |
| Isolation | `HASH` search schema elements make scoping mandatory; unscoped searches are rejected |
| Filtering | `INLINE_FILTER` search schema elements support conditions during search |

## More resources

- [DynamoDB vector search documentation](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/vector-search.html)
- [OpenAI embeddings guide](https://platform.openai.com/docs/guides/embeddings)
