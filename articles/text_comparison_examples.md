# Text comparison examples

The [OpenAI API embeddings endpoint](https://beta.openai.com/docs/guides/embeddings) can be used to measure relatedness or similarity between pieces of text.

By leveraging GPT-3's understanding of text, these embeddings [achieved state-of-the-art results](https://arxiv.org/abs/2201.10005) on benchmarks in unsupervised learning and transfer learning settings.

Embeddings can be used for semantic search, recommendations, cluster analysis, near-duplicate detection, and more.

For more information, read OpenAI's blog post announcements:

- [Introducing Text and Code Embeddings (Jan 2022)](https://openai.com/blog/introducing-text-and-code-embeddings/)
- [New and Improved Embedding Model (Dec 2022)](https://openai.com/blog/new-and-improved-embedding-model/)

For comparison with other embedding models, see [Massive Text Embedding Benchmark (MTEB) Leaderboard](https://huggingface.co/spaces/mteb/leaderboard)

## Semantic search

Embeddings can be used for search either by themselves or as a feature in a larger system.

The simplest way to use embeddings for search is as follows:

- Before the search (precompute):
  - Split your text corpus into chunks smaller than the token limit (8,191 tokens for `text-embedding-3-small`)
  - Embed each chunk of text
  - Store those embeddings in your own database or in a vector search provider like [Pinecone](https://www.pinecone.io), [Weaviate](https://weaviate.io) or [Qdrant](https://qdrant.tech)
- At the time of the search (live compute):
  - Embed the search query
  - Find the closest embeddings in your database
  - Return the top results

An example of how to use embeddings for search is shown in [Semantic_text_search_using_embeddings.ipynb](../examples/Semantic_text_search_using_embeddings.ipynb).

In more advanced search systems, the cosine similarity of embeddings can be used as one feature among many in ranking search results.

## Question answering

The best way to get reliably honest answers from GPT-3 is to give it source documents in which it can locate correct answers. Using the semantic search procedure above, you can cheaply search through a corpus of documents for relevant information and then give that information to GPT-3 via the prompt to answer a question. We demonstrate this in [Question_answering_using_embeddings.ipynb](../examples/Question_answering_using_embeddings.ipynb).

## Recommendations

Recommendations are quite similar to search, except that instead of a free-form text query, the inputs are items in a set.

An example of how to use embeddings for recommendations is shown in [Recommendation_using_embeddings.ipynb](../examples/Recommendation_using_embeddings.ipynb).

Similar to search, these cosine similarity scores can either be used on their own to rank items or as features in larger ranking algorithms.

## Customizing Embeddings

Although OpenAI's embedding model weights cannot be fine-tuned, you can nevertheless use training data to customize embeddings to your application.

In [Customizing_embeddings.ipynb](../examples/Customizing_embeddings.ipynb), we provide an example method for customizing your embeddings using training data. The idea of the method is to train a custom matrix to multiply embedding vectors by in order to get new customized embeddings. With good training data, this custom matrix will help emphasize the features relevant to your training labels. You can equivalently consider the matrix multiplication as (a) a modification of the embeddings or (b) a modification of the distance function used to measure the distances between embeddings.
