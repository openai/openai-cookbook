query = "how do bi-encoders work for sentence embeddings"
search = arxiv.Search(
    query=query, max_results=20, sort_by=arxiv.SortCriterion.Relevance
)