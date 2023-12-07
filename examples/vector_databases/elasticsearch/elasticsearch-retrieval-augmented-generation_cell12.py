index_mapping= {
    "properties": {
      "title_vector": {
          "type": "dense_vector",
          "dims": 1536,
          "index": "true",
          "similarity": "cosine"
      },
      "content_vector": {
          "type": "dense_vector",
          "dims": 1536,
          "index": "true",
          "similarity": "cosine"
      },
      "text": {"type": "text"},
      "title": {"type": "text"},
      "url": { "type": "keyword"},
      "vector_id": {"type": "long"}
      
    }
}

client.indices.create(index="wikipedia_vector_index", mappings=index_mapping)