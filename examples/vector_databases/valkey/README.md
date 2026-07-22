# Valkey

### What is Valkey?

At its core, Valkey is a fast, open‑source key‑value store that you can use as a cache, message broker, or database. Developers choose Valkey for its performance, its straightforward operational model, and the fact that it stays fully compatible with the Redis protocol while being developed openly under the Linux Foundation. Instead of relying on proprietary add‑ons, Valkey keeps its focus on a solid, high‑performance core and supports new capabilities—like vector search and advanced indexing—through openly maintained modules that evolve with the community.

### Deployment options

There are several ways to deploy Valkey for vector search applications:

**Local Development:**
- The quickest option is to use the valkey-bundle, which includes Valkey along with several modules that work together to provide a fast data store and query engine.
- This setup makes it easy to experiment with vector search locally and mirrors common Redis‑compatible workflows.

**Production Deployment:**
- Deploy Valkey on your own infrastructure using Docker or a native installation.
- Use Kubernetes for container orchestration when running Valkey at scale.
- Run Valkey on cloud providers such as AWS, GCP, or Azure using virtual machines or your existing deployment tooling.
- Since Valkey maintains full Redis compatibility, existing Redis deployment patterns, tools, and operational practices work seamlessly with Valkey.

**Cloud Marketplaces:**
As Valkey adoption grows, expect to see marketplace offerings on major cloud providers similar to Redis Enterprise.

### What is Search module?

Valkey‑Search is a high‑performance, open‑source Valkey module that adds native vector similarity search and secondary indexing capabilities to Valkey. It is optimized for AI workloads, delivering single‑digit millisecond latency and the ability to handle billions of vectors with over 99% recall. It supports both Approximate Nearest Neighbor (HNSW) and exact K‑Nearest Neighbors (KNN) search, along with complex filtering over Valkey Hash and Valkey‑JSON data. While its current focus is vector search, Valkey‑Search is evolving toward a full search engine with planned support for full‑text search and broader indexing features.

### Clients

For this cookbook, we use valkey-glide as the primary Valkey client. It’s the official high‑performance client for Valkey and is available across multiple programming languages, making it easy to integrate into a wide range of applications.
Current Approach:

- Basic Operations: Use valkey-glide for standard Valkey commands such as SET, GET, HSET, and others.
- Vector Search: Run FT commands directly through valkey-glide using its command execution APIs.
**Recommended Client Libraries:**

| Project | Language           | Use Case | Notes |
|----------|--------------------|----------|-------|
| [valkey-glide][valkey-glide-url] | Multiple languages | Primary Valkey client | Official, high-performance |
| [valkey-py][valkey-py-url] | Python             | Alternative Valkey client | Fork of redis-py |

[valkey-glide-url]: https://github.com/valkey-io/valkey-glide
[valkey-py-url]: https://github.com/valkey-io/valkey-py

### Cluster Support

Valkey supports clustering for horizontal scaling, and Search module can work in clustered environments for handling billions of documents across multiple nodes. This makes Valkey an excellent choice for large-scale vector search applications.

### Why Choose Valkey for Vector Search?

1. **Open Source Governance**: Valkey is developed under the Linux Foundation with transparent, community-driven governance
2. **Redis Compatibility**: Drop-in replacement for Redis with full protocol compatibility
3. **Performance**: Maintains the high performance characteristics of Redis
4. **Vector Search**: Supports vector similarity search
5. **Community**: Growing open-source community and ecosystem
6. **Future-Proof**: Independent development ensures long-term availability and innovation

### More Resources

For more information on using Valkey as a vector database:

- [Valkey Official Documentation](https://valkey.io/) - Official Valkey documentation
- [Vector Similarity Search: From Basics to Production](https://mlops.community/vector-similarity-search-from-basics-to-production/) - Introductory guide to vector search
- [Valkey GitHub Repository](https://github.com/valkey-io/valkey) - Source code and community discussions
