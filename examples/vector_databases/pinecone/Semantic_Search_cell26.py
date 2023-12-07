query = "What was the cause of the major recession in the early 20th century?"

# create the query embedding
xq = openai.Embedding.create(input=query, engine=MODEL)['data'][0]['embedding']

# query, returning the top 5 most similar results
res = index.query([xq], top_k=5, include_metadata=True)

for match in res['matches']:
    print(f"{match['score']:.2f}: {match['metadata']['text']}")