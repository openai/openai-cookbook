query = "What caused the 1929 Great Depression?"

xq = openai.Embedding.create(input=query, engine=MODEL)['data'][0]['embedding']