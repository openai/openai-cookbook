def near_text_weaviate(query, collection_name):
    
    nearText = {
        "concepts": [query],
        "distance": 0.7,
    }

    properties = [
        "title", "content",
        "_additional {certainty distance}"
    ]

    query_result = (
        client.query
        .get(collection_name, properties)
        .with_near_text(nearText)
        .with_limit(20)
        .do()
    )["data"]["Get"][collection_name]
    
    print (f"Objects returned: {len(query_result)}")
    
    return query_result