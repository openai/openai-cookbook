def hybrid_query_weaviate(query, collection_name, alpha_val):
    
    nearText = {
        "concepts": [query],
        "distance": 0.7,
    }

    properties = [
        "title", "content", "url",
        "_additional { score }"
    ]

    result = (
        client.query
        .get(collection_name, properties)
        .with_hybrid(nearText, alpha=alpha_val)
        .with_limit(10)
        .do()
    )
    
    # Check for errors
    if ("errors" in result):
        print ("\033[91mYou probably have run out of OpenAI API calls for the current minute – the limit is set at 60 per minute.")
        raise Exception(result["errors"][0]['message'])
    
    return result["data"]["Get"][collection_name]