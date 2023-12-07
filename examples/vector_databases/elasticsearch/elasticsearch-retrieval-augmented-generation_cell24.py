response = client.search(
  index = "wikipedia_vector_index",
  knn={
      "field": "content_vector",
      "query_vector":  question_embedding["data"][0]["embedding"],
      "k": 10,
      "num_candidates": 100
    }
)
pretty_response(response)

top_hit_summary = response['hits']['hits'][0]['_source']['text'] # Store content of top hit for final step