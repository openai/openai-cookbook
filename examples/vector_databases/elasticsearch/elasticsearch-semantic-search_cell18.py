print(client.search(index="wikipedia_vector_index", body={
    "_source": {
        "excludes": ["title_vector", "content_vector"]
    },
    "query": {
        "match": {
            "text": {
                "query": "Hummingbird"
            }
        }
    }
}))