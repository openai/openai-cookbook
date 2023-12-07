# establish a cache of embeddings to avoid recomputing
# cache is a dict of tuples (text, engine) -> embedding
try:
    with open(embedding_cache_path, "rb") as f:
        embedding_cache = pickle.load(f)
except FileNotFoundError:
    precomputed_embedding_cache_path = "https://cdn.openai.com/API/examples/data/snli_embedding_cache.pkl"
    embedding_cache = pd.read_pickle(precomputed_embedding_cache_path)


# this function will get embeddings from the cache and save them there afterward
def get_embedding_with_cache(
    text: str,
    engine: str = default_embedding_engine,
    embedding_cache: dict = embedding_cache,
    embedding_cache_path: str = embedding_cache_path,
) -> list:
    if (text, engine) not in embedding_cache.keys():
        # if not in cache, call API to get embedding
        embedding_cache[(text, engine)] = get_embedding(text, engine)
        # save embeddings cache to disk after each update
        with open(embedding_cache_path, "wb") as embedding_cache_file:
            pickle.dump(embedding_cache, embedding_cache_file)
    return embedding_cache[(text, engine)]


# create column of embeddings
for column in ["text_1", "text_2"]:
    df[f"{column}_embedding"] = df[column].apply(get_embedding_with_cache)

# create column of cosine similarity between embeddings
df["cosine_similarity"] = df.apply(
    lambda row: cosine_similarity(row["text_1_embedding"], row["text_2_embedding"]),
    axis=1,
)
