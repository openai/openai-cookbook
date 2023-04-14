# Typesense

Typesense is an open source, in-memory search engine, that you can either [self-host](https://typesense.org/docs/guide/install-typesense.html#option-2-local-machine-self-hosting) or run on [Typesense Cloud](https://cloud.typesense.org/).

## Why Typesense?

Typesense focuses on performance by storing the entire index in RAM (with a backup on disk) and also focuses on providing an out-of-the-box developer experience by simplifying available options and setting good defaults. 

It also lets you combine attribute-based filtering together with vector queries, to fetch the most relevant documents.

### Other features

Besides vector storage and search, Typesense also offers the following features:

- Typo Tolerance: Handles typographical errors elegantly, out-of-the-box.
- Tunable Ranking: Easy to tailor your search results to perfection.
- Sorting: Dynamically sort results based on a particular field at query time (helpful for features like "Sort by Price (asc)").
- Faceting & Filtering: Drill down and refine results.
- Grouping & Distinct: Group similar results together to show more variety.
- Federated Search: Search across multiple collections (indices) in a single HTTP request.
- Scoped API Keys: Generate API keys that only allow access to certain records, for multi-tenant applications.
- Synonyms: Define words as equivalents of each other, so searching for a word will also return results for the synonyms defined.
- Curation & Merchandizing: Boost particular records to a fixed position in the search results, to feature them.
- Raft-based Clustering: Set up a distributed cluster that is highly available.
- Seamless Version Upgrades: As new versions of Typesense come out, upgrading is as simple as swapping out the binary and restarting Typesense.
- No Runtime Dependencies: Typesense is a single binary that you can run locally or in production with a single command.

## How To

- To learn more about how to use Typesense with OpenAI embeddings, see the notebook here for an example: [examples/vector_databases/Using_vector_databases_for_embeddings_search.ipynb](/examples/vector_databases/Using_vector_databases_for_embeddings_search.ipynb)
- To learn more about Typesense's vector search feature, read the docs here: [https://typesense.org/docs/0.24.1/api/vector-search.html](https://typesense.org/docs/0.24.1/api/vector-search.html).
