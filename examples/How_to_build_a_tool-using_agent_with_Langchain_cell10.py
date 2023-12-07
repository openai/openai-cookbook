# Initiate a Search tool - note you'll need to have set SERPAPI_API_KEY as an environment variable as per the above instructions
search = SerpAPIWrapper()

# Define a list of tools
tools = [
    Tool(
        name = "Search",
        func=search.run,
        description="useful for when you need to answer questions about current events"
    )
]