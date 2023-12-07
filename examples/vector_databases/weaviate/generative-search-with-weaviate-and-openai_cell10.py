def generative_search_group(query, collection_name):
    generateTask = "Explain what these have in common"

    result = (
        client.query
        .get(collection_name, ["title", "content", "url"])
        .with_near_text({ "concepts": [query], "distance": 0.7 })
        .with_generate(grouped_task=generateTask)
        .with_limit(5)
        .do()
    )
    
    # Check for errors
    if ("errors" in result):
        print ("\033[91mYou probably have run out of OpenAI API calls for the current minute – the limit is set at 60 per minute.")
        raise Exception(result["errors"][0]['message'])
    
    return result["data"]["Get"][collection_name]