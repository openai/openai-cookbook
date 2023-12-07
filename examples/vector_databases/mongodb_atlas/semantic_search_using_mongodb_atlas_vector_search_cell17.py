collection.create_search_index(
    {"definition":
        {"mappings": {"dynamic": True, "fields": {
            EMBEDDING_FIELD_NAME : {
                "dimensions": 1536,
                "similarity": "dotProduct",
                "type": "knnVector"
                }}}},
     "name": ATLAS_VECTOR_SEARCH_INDEX_NAME
    }
)