expanded_tools = [
    Tool(
        name = "Search",
        func=search.run,
        description="useful for when you need to answer questions about current events"
    ),
    Tool(
        name = 'Knowledge Base',
        func=podcast_retriever.run,
        description="Useful for general questions about how to do things and for details on interesting topics. Input should be a fully formed question."
    )
]