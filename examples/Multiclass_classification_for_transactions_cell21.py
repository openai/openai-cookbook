from utils.embeddings_utils import get_embedding

df['babbage_similarity'] = df.combined.apply(lambda x: get_embedding(x, model='text-similarity-babbage-001'))
df['babbage_search'] = df.combined.apply(lambda x: get_embedding(x, model='text-search-babbage-doc-001'))
df.to_csv(embedding_path)
