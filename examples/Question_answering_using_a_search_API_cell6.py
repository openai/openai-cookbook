QUERIES_INPUT = f"""
You have access to a search API that returns recent news articles.
Generate an array of search queries that are relevant to this question.
Use a variation of related keywords for the queries, trying to be as general as possible.
Include as many queries as you can think of, including and excluding terms.
For example, include queries like ['keyword_1 keyword_2', 'keyword_1', 'keyword_2'].
Be creative. The more queries you include, the more likely you are to find relevant results.

User question: {USER_QUESTION}

Format: {{"queries": ["query_1", "query_2", "query_3"]}}
"""

queries = json_gpt(QUERIES_INPUT)["queries"]

# Let's include the original question as well for good measure
queries.append(USER_QUESTION)

queries