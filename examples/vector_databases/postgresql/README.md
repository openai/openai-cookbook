
# PostgreSQL as a Vector Database

PostgreSQL is a free and open-source relational database known for its extensibility. It has a rich ecosystem of extensions and solutions that allow us to use PostgreSQL as a vector database for general-purpose AI applications.

* [Pgvector](https://github.com/pgvector/pgvector) is an extension that provides PostgreSQL with all the essential capabilities needed for a vector database. With pgvector, you can efficiently store vectors/embeddings in PostgreSQL, perform vector similarity search, optimize data access with IVFFlat and HNSW indexes, and much more.
* [pg_vectorize](https://github.com/tembo-io/pg_vectorize) is an extension that automates the transformation and orchestration of text to embeddings, allowing you to perform vector and semantic search on existing data with as little as two function calls.
* [PostgresML](https://github.com/postgresml/postgresml) is a machine learning extension for PostgreSQL that enables you to perform training and inference on text and tabular data using SQL queries. With PostgresML, you can seamlessly integrate machine learning models into your PostgreSQL database and execute them within the database.
* [azure_ai](https://learn.microsoft.com/en-us/azure/postgresql/flexible-server/generative-ai-azure-overview) is an extension that allows you to call various Azure AI services, including Azure OpenAI and Azure Cognitive Services, from within the database. Note that presently, azure_ai is available for Azure Database for PostgreSQL only.
* [YugabyteDB with pgvector](https://docs.yugabyte.com/preview/explore/ysql-language-features/pg-extensions/extension-pgvector/) - YugabyteDB is a distributed SQL database built on PostgreSQL. It's feature and runtime compatible with PostgreSQL, allowing you to scale out Postgres workloads across a shared-nothing distributed database cluster.

## Notebooks and Guides

Below is a list of notebooks and guides available on the OpenAI Cookbook:
* [Getting Started With PostgreSQL pgvector](getting_started_with_postgresql_pgvector.ipynb)
