query = "Famous battles in Scottish history"

# creates embedding vector from user query
embed = openai.Embedding.create(
    input=query,
    model="text-embedding-ada-002",
)["data"][0]["embedding"]

# query the database to find the top K similar content to the given query
top_k = 10
results = client.query(f"""
SELECT id, url, title, distance(content_vector, {embed}) as dist
FROM default.articles
ORDER BY dist
LIMIT {top_k}
""")

# display results
for i, r in enumerate(results.named_results()):
    print(i+1, r['title'])