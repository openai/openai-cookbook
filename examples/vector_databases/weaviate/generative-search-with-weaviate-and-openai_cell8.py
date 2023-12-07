def generative_search_per_item(query, collection_name):
    prompt = "Summarize in a short tweet the following content: {content}"

    result = (
        client.query
        .get(collection_name, ["title", "content", "url"])
        .with_near_text({ "concepts": [query], "distance": 0.7 })
        .with_limit(5)
        .with_generate(single_prompt=prompt)
        .do()
    )
    
    # Check for errors
    if ("errors" in result):
        print ("\033[91mYou probably have run out of OpenAI API calls for the current minute – the limit is set at 60 per minute.")
        raise Exception(result["errors"][0]['message'])
    
    return result["data"]["Get"][collection_name]