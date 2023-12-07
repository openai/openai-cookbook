
def query_results(query, k):
  results = collection.aggregate([
    {
        '$vectorSearch': {
            "index": ATLAS_VECTOR_SEARCH_INDEX_NAME,
            "path": EMBEDDING_FIELD_NAME,
            "queryVector": generate_embedding(query),
            "numCandidates": 50,
            "limit": 5,
        }
    }
    ])
  return results