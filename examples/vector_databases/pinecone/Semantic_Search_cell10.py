# we can extract embeddings to a list
embeds = [record['embedding'] for record in res['data']]
len(embeds)