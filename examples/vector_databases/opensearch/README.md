# OpenSearch

OpenSearch is a popular open-source search/analytics engine and [vector database](https://opensearch.org/platform/search/vector-database.html).
With OpenSearch you can efficiently store and query any kind of data including your vector embeddings at scale. 

[Aiven](https://go.aiven.io/openai-opensearch-aiven) provides a way to experience the best of open source data technologies, including OpenSearch, in a secure, well integrated, scalable and trustable data platform. [Aiven for OpenSearch](https://aiven.io/opensearch) allows you to experience OpenSearch in minutes, on all the major cloud vendor and regions, supported by a self-healing platform with a 99.99% SLA.

For technical details, refer to the [OpenSearch documentation](https://opensearch.org/docs/latest/search-plugins/knn/index/).

## OpenAI cookbook notebooks 📒

Check out our notebooks in this repo for working with OpenAI, using OpenSearch as your vector database.

### [Semantic search](aiven-opensearch-semantic-search.ipynb)

In this notebook you'll learn how to:

 - Index the OpenAI Wikipedia embeddings dataset into OpenSearch
 - Encode a question with the `text-embedding-3-small` model
 - Perform a semantic search