# Cassandra / Astra DB

The example notebooks in this directory show how to use the Vector
Search capabilities available today in **DataStax Astra DB**, a serverless
Database-as-a-Service built on Apache Cassandra®.

Moreover, support for vector-oriented workloads is making its way to the
next major release of Cassandra, so that the code examples in this folder
are designed to work equally well on it as soon as the vector capabilities
get released.

If you want to know more about Astra DB and its Vector Search capabilities,
head over to [astra.datastax.com](https://docs.datastax.com/en/astra-serverless/docs/vector-search/overview.html) or try out one
of these hands-on notebooks straight away:

### Example notebooks

The following examples show how easily OpenAI and DataStax Astra DB can
work together to power vector-based AI applications. You can run them either
with your local Jupyter engine or as Colab notebooks:

| Use case | Framework | Notebook | Google Colab |
| -------- | --------- | -------- | ------------ |
| Search/generate quotes | CassIO | [Notebook](./Philosophical_Quotes_cassIO.ipynb) | [![Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/openai/openai-cookbook/blob/main/examples/vector_databases/cassandra_astradb/Philosophical_Quotes_cassIO.ipynb) |
| Search/generate quotes | Plain Cassandra language | [Notebook](./Philosophical_Quotes_CQL.ipynb) | [![Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/openai/openai-cookbook/blob/main/examples/vector_databases/cassandra_astradb/Philosophical_Quotes_CQL.ipynb) |

### Vector similarity, visual representation

![3_vector_space](https://user-images.githubusercontent.com/14221764/262321363-c8c625c1-8be9-450e-8c68-b1ed518f990d.png)
