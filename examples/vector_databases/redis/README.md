
# Redis

### What is Redis?

Most developers from a web services background are probably familiar with Redis. At it's core, Redis is an open-source key-value store that can be used as a cache, message broker, and database. Developers choice Redis because it is fast, has a large ecosystem of client libraries, and has been deployed by major enterprises for years.

In addition to the traditional uses of Redis. Redis also provides [Redis Modules](https://redis.io/modules) which are a way to extend Redis with new capabilities, commands and data types. Example modules include [RedisJSON](https://redis.io/docs/stack/json/), [RedisTimeSeries](https://redis.io/docs/stack/timeseries/), [RedisBloom](https://redis.io/docs/stack/bloom/) and [RediSearch](https://redis.io/docs/stack/search/).


### Deployment options

There are a number of ways to deploy Redis. For local development, the quickest method is to use the [Redis Stack docker container](https://hub.docker.com/r/redis/redis-stack) which we will use here. Redis Stack contains a number of Redis modules that can be used together to create a fast, multi-model data store and query engine.

For production use cases, The easiest way to get started is to use the [Redis Cloud](https://redislabs.com/redis-enterprise-cloud/overview/) service. Redis Cloud is a fully managed Redis service. You can also deploy Redis on your own infrastructure using [Redis Enterprise](https://redislabs.com/redis-enterprise/overview/). Redis Enterprise is a fully managed Redis service that can be deployed in kubernetes, on-premises or in the cloud.

Additionally, every major cloud provider ([AWS Marketplace](https://aws.amazon.com/marketplace/pp/prodview-e6y7ork67pjwg?sr=0-2&ref_=beagle&applicationId=AWSMPContessa), [Google Marketplace](https://console.cloud.google.com/marketplace/details/redislabs-public/redis-enterprise?pli=1), or [Azure Marketplace](https://azuremarketplace.microsoft.com/en-us/marketplace/apps/garantiadata.redis_enterprise_1sp_public_preview?tab=Overview)) offers Redis Enterprise in a marketplace offering.


### What is RediSearch?

RediSearch is a [Redis module](https://redis.io/modules) that provides querying, secondary indexing, full-text search and vector search for Redis. To use RediSearch, you first declare indexes on your Redis data. You can then use the RediSearch clients to query that data. For more information on the feature set of RediSearch, see the [RediSearch documentation](https://redis.io/docs/stack/search/).


### Features

RediSearch uses compressed, inverted indexes for fast indexing with a low memory footprint. RediSearch indexes enhance Redis by providing exact-phrase matching, fuzzy search, and numeric filtering, among many other features. Such as:

* Full-Text indexing of multiple fields in Redis hashes
* Incremental indexing without performance loss
* Vector similarity search
* Document ranking (using [tf-idf](https://en.wikipedia.org/wiki/Tf%E2%80%93idf), with optional user-provided weights)
* Field weighting
* Complex boolean queries with AND, OR, and NOT operators
* Prefix matching, fuzzy matching, and exact-phrase queries
* Support for [double-metaphone phonetic matching](https://redis.io/docs/stack/search/reference/phonetic_matching/)
* Auto-complete suggestions (with fuzzy prefix suggestions)
* Stemming-based query expansion in [many languages](https://redis.io/docs/stack/search/reference/stemming/) (using [Snowball](http://snowballstem.org/))
* Support for Chinese-language tokenization and querying (using [Friso](https://github.com/lionsoul2014/friso))
* Numeric filters and ranges
* Geospatial searches using [Redis geospatial indexing](/commands/georadius)
* A powerful aggregations engine
* Supports for all utf-8 encoded text
* Retrieve full documents, selected fields, or only the document IDs
* Sorting results (for example, by creation date)
* JSON support through RedisJSON


### Clients

Given the large ecosystem around Redis, there are most likely client libraries in the language you need. You can use any standard Redis client library to run RediSearch commands, but it's easiest to use a library that wraps the RediSearch API. Below are a few examples, but you can find more client libraries [here](https://redis.io/resources/clients/).

| Project | Language | License | Author | Stars |
|----------|---------|--------|---------|-------|
| [jedis][jedis-url] | Java | MIT | [Redis][redis-url] | ![Stars][jedis-stars] |
| [redis-py][redis-py-url] | Python | MIT | [Redis][redis-url] | ![Stars][redis-py-stars] |
| [node-redis][node-redis-url] | Node.js | MIT | [Redis][redis-url] | ![Stars][node-redis-stars] |
| [nredisstack][nredisstack-url] | .NET | MIT | [Redis][redis-url] | ![Stars][nredisstack-stars] |

[redis-url]: https://redis.com

[redis-py-url]: https://github.com/redis/redis-py
[redis-py-stars]: https://img.shields.io/github/stars/redis/redis-py.svg?style=social&amp;label=Star&amp;maxAge=2592000
[redis-py-package]: https://pypi.python.org/pypi/redis

[jedis-url]: https://github.com/redis/jedis
[jedis-stars]: https://img.shields.io/github/stars/redis/jedis.svg?style=social&amp;label=Star&amp;maxAge=2592000
[Jedis-package]: https://search.maven.org/artifact/redis.clients/jedis

[nredisstack-url]: https://github.com/redis/nredisstack
[nredisstack-stars]: https://img.shields.io/github/stars/redis/nredisstack.svg?style=social&amp;label=Star&amp;maxAge=2592000
[nredisstack-package]: https://www.nuget.org/packages/nredisstack/

[node-redis-url]: https://github.com/redis/node-redis
[node-redis-stars]: https://img.shields.io/github/stars/redis/node-redis.svg?style=social&amp;label=Star&amp;maxAge=2592000
[node-redis-package]: https://www.npmjs.com/package/redis

[redis-om-python-url]: https://github.com/redis/redis-om-python
[redis-om-python-author]: https://redis.com
[redis-om-python-stars]: https://img.shields.io/github/stars/redis/redis-om-python.svg?style=social&amp;label=Star&amp;maxAge=2592000

[redisearch-go-url]: https://github.com/RediSearch/redisearch-go
[redisearch-go-author]: https://redis.com
[redisearch-go-stars]: https://img.shields.io/github/stars/RediSearch/redisearch-go.svg?style=social&amp;label=Star&amp;maxAge=2592000

[redisearch-api-rs-url]: https://github.com/RediSearch/redisearch-api-rs
[redisearch-api-rs-author]: https://redis.com
[redisearch-api-rs-stars]: https://img.shields.io/github/stars/RediSearch/redisearch-api-rs.svg?style=social&amp;label=Star&amp;maxAge=2592000


### Deployment Options

There are many ways to deploy Redis with RediSearch. The easiest way to get started is to use Docker, but there are are many potential options for deployment such as

- [Redis Cloud](https://redis.com/redis-enterprise-cloud/overview/)
- Cloud marketplaces: [AWS Marketplace](https://aws.amazon.com/marketplace/pp/prodview-e6y7ork67pjwg?sr=0-2&ref_=beagle&applicationId=AWSMPContessa), [Google Marketplace](https://console.cloud.google.com/marketplace/details/redislabs-public/redis-enterprise?pli=1), or [Azure Marketplace](https://azuremarketplace.microsoft.com/en-us/marketplace/apps/garantiadata.redis_enterprise_1sp_public_preview?tab=Overview)
- On-premise: [Redis Enterprise Software](https://redis.com/redis-enterprise-software/overview/)
- Kubernetes: [Redis Enterprise Software on Kubernetes](https://docs.redis.com/latest/kubernetes/)
- [Docker (RediSearch)](https://hub.docker.com/r/redislabs/redisearch)
- [Docker (Redis Stack)](https://hub.docker.com/r/redis/redis-stack)


### Cluster support

RediSearch has a distributed cluster version that scales to billions of documents across hundreds of servers. At the moment, distributed RediSearch is available as part of [Redis Enterprise Cloud](https://redis.com/redis-enterprise-cloud/overview/) and [Redis Enterprise Software](https://redis.com/redis-enterprise-software/overview/).

See [RediSearch on Redis Enterprise](https://redis.com/modules/redisearch/) for more information.

### Examples

- [Product Search](https://github.com/RedisVentures/redis-product-search) - eCommerce product search (with image and text)
- [Product Recommendations with DocArray / Jina](https://github.com/jina-ai/product-recommendation-redis-docarray) - Content-based product recommendations example with Redis and DocArray.
- [Redis VSS in RecSys](https://github.com/RedisVentures/Redis-Recsys) - 3 end-to-end Redis & NVIDIA Merlin Recommendation System Architectures.
- [Azure OpenAI Embeddings Q&A](https://github.com/ruoccofabrizio/azure-open-ai-embeddings-qna) - OpenAI and Redis as a Q&A service on Azure.
- [ArXiv Paper Search](https://github.com/RedisVentures/redis-arXiv-search) - Semantic search over arXiv scholarly papers


### More Resources

For more information on how to use Redis as a vector database, check out the following resources:

- [Redis Vector Similarity Docs](https://redis.io/docs/stack/search/reference/vectors/) - Redis official docs for Vector Search.
- [Redis-py Search Docs](https://redis.readthedocs.io/en/latest/redismodules.html#redisearch-commands) - Redis-py client library docs for RediSearch.
- [Vector Similarity Search: From Basics to Production](https://mlops.community/vector-similarity-search-from-basics-to-production/) - Introductory blog post to VSS and Redis as a VectorDB.
- [AI-Powered Document Search](https://datasciencedojo.com/blog/ai-powered-document-search/) - Blog post covering AI Powered Document Search Use Cases & Architectures.
- [Vector Database Benchmarks](https://jina.ai/news/benchmark-vector-search-databases-with-one-million-data/) - Jina AI VectorDB benchmarks comparing Redis against others.