# Use cases for embeddings

OpenAI embeddings represent text as vectors that can be compared by distance.
They are useful when an application needs to search, group, rank, recommend, or
classify text by meaning rather than exact keyword overlap.

For current model details, API parameters, pricing, and limits, see the
[embeddings guide](https://developers.openai.com/api/docs/guides/embeddings)
and [embeddings API reference](https://developers.openai.com/api/docs/api-reference/embeddings).
Most examples in this cookbook use `text-embedding-3-small` as a good default;
use `text-embedding-3-large` when higher retrieval quality is worth the larger
vectors. Both models also support the `dimensions` parameter, which can shorten
vectors when storage, latency, or vector database limits matter.

## Basic workflow

1. Split source text into chunks that fit within the embedding model's input
   limit.
2. Create one embedding per chunk, item, label, or query.
3. Store each vector with the text and metadata needed to show or filter
   results.
4. For a live query or item, create a new embedding with the same model.
5. Compare vectors with cosine similarity, dot product, or the distance metric
   supported by your vector database.
6. Return the best matches, use them as ranking features, or pass the retrieved
   text into a model as context.

For larger corpora, store embeddings in a vector database or search service.
The cookbook's [vector database examples](../examples/vector_databases/README.md)
show integrations for common providers.

## Semantic search

Embeddings let search systems find text with similar meaning even when the
query and result do not share the same words. A typical semantic search pipeline
embeds documents ahead of time, embeds the user's query at request time, and
ranks documents by vector similarity.

See [Semantic_text_search_using_embeddings.ipynb](../examples/Semantic_text_search_using_embeddings.ipynb)
for a minimal search example.

## Question answering over source material

For question answering over private or domain-specific content, use embeddings
to retrieve the most relevant source passages, then provide those passages to a
text generation model as context. This pattern is often called retrieval
augmented generation.

See [Question_answering_using_embeddings.ipynb](../examples/Question_answering_using_embeddings.ipynb)
for an example that answers questions from retrieved source text.

## Recommendations and similarity ranking

Recommendations use the same distance idea as search, but the query is an item
instead of a free-form text string. Embed the items, compare one item embedding
against the others, and rank the nearest neighbors.

See [Recommendation_using_embeddings.ipynb](../examples/Recommendation_using_embeddings.ipynb)
for a nearest-neighbor recommendation example.

## Classification, clustering, and regression

Embeddings can be used as compact text features for machine learning workflows.
You can cluster related items, classify text by comparing it to embedded labels,
or train lightweight models on top of embedding vectors.

Relevant examples:

- [Classification_using_embeddings.ipynb](../examples/Classification_using_embeddings.ipynb)
- [Zero-shot_classification_with_embeddings.ipynb](../examples/Zero-shot_classification_with_embeddings.ipynb)
- [Clustering.ipynb](../examples/Clustering.ipynb)
- [Regression_using_embeddings.ipynb](../examples/Regression_using_embeddings.ipynb)

## Customizing embedding behavior

If raw vector similarity does not match your product's notion of relevance, use
labeled examples to learn a task-specific threshold, reranker, classifier, or
linear transformation on top of embeddings. This keeps the base embedding model
unchanged while adapting the distance function to your use case.

See [Customizing_embeddings.ipynb](../examples/Customizing_embeddings.ipynb)
for an example of learning a custom matrix that changes how embedding vectors
are compared.
