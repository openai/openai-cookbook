def qna(query, collection_name):
    
    properties = [
        "title", "content", "url",
        "_additional { answer { hasAnswer property result startPosition endPosition } distance }"
    ]

    ask = {
        "question": query,
        "properties": ["content"]
    }

    result = (
        client.query
        .get(collection_name, properties)
        .with_ask(ask)
        .with_limit(1)
        .do()
    )
    
    # Check for errors
    if ("errors" in result):
        print ("\033[91mYou probably have run out of OpenAI API calls for the current minute – the limit is set at 60 per minute.")
        raise Exception(result["errors"][0]['message'])
    
    return result["data"]["Get"][collection_name]